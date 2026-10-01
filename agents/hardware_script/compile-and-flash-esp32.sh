#!/usr/bin/env bash

# Install the pinned ESP-IDF toolchain, configure the IEMP firmware, securely
# prompt for its MQTT password, build it, and flash one USB-connected ESP32.

set -Eeuo pipefail
umask 077

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly FIRMWARE_DIR="${REPO_ROOT}/firmware"
readonly IDF_VERSION="5.5.4"
readonly LOCAL_USER="$(id -un)"

SKIP_HOST_INSTALL=false
FORCE_CONFIGURE=false
MONITOR=false
SERIAL_PORT=""
ESP_IDF_DIR="${IEMP_ESP_IDF_DIR:-}"
SUDO=()

log() {
  printf '[iemp-firmware] %s\n' "$*"
}

fail() {
  printf '[iemp-firmware] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: agents/hardware_script/compile-and-flash-esp32.sh [options]

Install ESP-IDF 5.5.4, compile the IEMP firmware, and flash a USB-connected
ESP32. The first run opens menuconfig for device, Wi-Fi, broker, and sensor setup.
Every run asks for the device's MQTT password without displaying it.

Options:
  --port DEVICE          Serial device to flash, such as /dev/ttyUSB0.
                         When omitted, exactly one connected ESP32 port is detected.
  --configure            Open menuconfig even when sdkconfig is already valid.
  --monitor              Open the serial monitor after flashing (exit with Ctrl+]).
  --idf-dir DIRECTORY    ESP-IDF checkout location. The default is under
                         $XDG_DATA_HOME/iemp or $HOME/.local/share/iemp.
  --skip-host-install    Do not install Debian/Ubuntu/Raspberry Pi OS packages.
  -h, --help             Show this help text.

Run as your normal user, not with sudo. Connect one ESP32 with a data-capable
USB cable before starting. Existing sdkconfig and ESP-IDF installations are
validated and reused. The MQTT password is stored in the ignored sdkconfig and
embedded in the firmware image. It never runs a full-chip erase or intentionally
erases NVS.
EOF
}

while (($# > 0)); do
  case "$1" in
    --port)
      (($# >= 2)) || fail "--port requires a device path"
      SERIAL_PORT="$2"
      shift 2
      ;;
    --configure)
      FORCE_CONFIGURE=true
      shift
      ;;
    --monitor)
      MONITOR=true
      shift
      ;;
    --idf-dir)
      (($# >= 2)) || fail "--idf-dir requires a directory"
      ESP_IDF_DIR="$2"
      shift 2
      ;;
    --skip-host-install)
      SKIP_HOST_INSTALL=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1 (use --help)"
      ;;
  esac
done

[[ "$(uname -s)" == "Linux" ]] || fail "This firmware helper supports Linux only"
case "$(uname -m)" in
  x86_64 | aarch64 | arm64) ;;
  *) fail "A 64-bit x86_64 or ARM64 Linux installation is required" ;;
esac
((EUID != 0)) || fail "Run this script as your normal user; it invokes sudo only for host packages"
[[ -f "${FIRMWARE_DIR}/CMakeLists.txt" ]] || fail "Cannot find the firmware project at ${FIRMWARE_DIR}"
[[ -t 0 && -t 1 && -r /dev/tty && -w /dev/tty ]] ||
  fail "An interactive terminal is required to enter the MQTT password"

if [[ -z "$ESP_IDF_DIR" ]]; then
  [[ -n "${HOME:-}" ]] || fail "HOME is not set; pass --idf-dir explicitly"
  ESP_IDF_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/iemp/esp-idf-v${IDF_VERSION}"
fi

if command -v sudo >/dev/null 2>&1; then
  SUDO=(sudo)
fi

install_host_packages() {
  local package
  local packages_are_installed=true
  local -a packages=(
    git wget flex bison gperf python3 python3-pip python3-venv
    cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
  )

  if $SKIP_HOST_INSTALL; then
    log "Skipping host package installation"
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    for package in "${packages[@]}"; do
      if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$'; then
        packages_are_installed=false
        break
      fi
    done
    if $packages_are_installed; then
      log "ESP-IDF host packages are already installed"
      return
    fi

    ((${#SUDO[@]} > 0)) || fail "sudo is required to install host packages"
    log "Installing ESP-IDF build and USB dependencies"
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" apt-get install -y "${packages[@]}"
    return
  fi

  fail "Automatic dependency installation supports Raspberry Pi OS, Debian, and Ubuntu; install ESP-IDF prerequisites for this distribution and rerun with --skip-host-install"
}

verify_host_tools() {
  local tool
  for tool in git wget flex bison gperf python3 cmake ninja; do
    command -v "$tool" >/dev/null 2>&1 || fail "Required host tool is missing: ${tool}"
  done
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' ||
    fail "Python 3.9 or newer is required by this ESP-IDF setup"
}

install_esp_idf() {
  local actual_commit expected_commit

  if [[ ! -e "$ESP_IDF_DIR" ]]; then
    log "Cloning ESP-IDF v${IDF_VERSION} into ${ESP_IDF_DIR}"
    mkdir -p -- "$(dirname -- "$ESP_IDF_DIR")"
    git clone --depth 1 --shallow-submodules --branch "v${IDF_VERSION}" --recursive \
      https://github.com/espressif/esp-idf.git "$ESP_IDF_DIR" ||
      fail "ESP-IDF download failed; rerun the script. If it fails again, check the network and storage for errors"
  else
    [[ -d "${ESP_IDF_DIR}/.git" ]] ||
      fail "Existing ESP-IDF path is not a Git checkout: ${ESP_IDF_DIR}"
    expected_commit="$(git -C "$ESP_IDF_DIR" rev-parse --verify "v${IDF_VERSION}^{commit}" 2>/dev/null)" ||
      fail "Existing ESP-IDF checkout does not contain tag v${IDF_VERSION}: ${ESP_IDF_DIR}"
    actual_commit="$(git -C "$ESP_IDF_DIR" rev-parse --verify HEAD)"
    [[ "$actual_commit" == "$expected_commit" ]] ||
      fail "Existing ESP-IDF checkout is not at v${IDF_VERSION}: ${ESP_IDF_DIR}"
    log "Reusing ESP-IDF v${IDF_VERSION} at ${ESP_IDF_DIR}"
    git -C "$ESP_IDF_DIR" submodule update --init --recursive
  fi

  log "Installing/reusing the ESP32 compiler and Python tools"
  "${ESP_IDF_DIR}/install.sh" esp32

  # ESP-IDF's supported activation script sets IDF_PATH, the Python environment,
  # compiler paths, and idf.py for this process only.
  # shellcheck disable=SC1091
  source "${ESP_IDF_DIR}/export.sh"
  command -v idf.py >/dev/null 2>&1 || fail "ESP-IDF activation did not provide idf.py"
  idf.py --version | grep -F "v${IDF_VERSION}" >/dev/null ||
    fail "Activated ESP-IDF does not report v${IDF_VERSION}"
}

configuration_is_valid() {
  IEMP_SDKCONFIG="${FIRMWARE_DIR}/sdkconfig" IEMP_REQUIRE_MQTT_PASSWORD="${1:-true}" python3 <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["IEMP_SDKCONFIG"])
if not path.is_file():
    raise SystemExit(1)

settings = {}
for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
    if "=" not in line or line.startswith("#"):
        continue
    key, value = line.split("=", 1)
    settings[key] = value


def string_value(key):
    raw = settings.get(key, "")
    if not raw.startswith('"'):
        return ""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    return value if isinstance(value, str) else ""


invalid = []
device_id = string_value("CONFIG_IEMP_DEVICE_ID")
ssid = string_value("CONFIG_IEMP_WIFI_SSID")
wifi_password = string_value("CONFIG_IEMP_WIFI_PASSWORD")
mqtt_host = string_value("CONFIG_IEMP_MQTT_HOST")
mqtt_password = string_value("CONFIG_IEMP_MQTT_PASSWORD")

if not 1 <= len(device_id.encode()) <= 128 or any(
    char in "/+#" or ord(char) < 32 or ord(char) == 127 for char in device_id
):
    invalid.append("registered device ID")
if not 1 <= len(ssid.encode()) <= 32:
    invalid.append("Wi-Fi SSID")
if not 8 <= len(wifi_password.encode()) <= 63:
    invalid.append("Wi-Fi passphrase")
if not mqtt_host:
    invalid.append("MQTT host")
if os.environ["IEMP_REQUIRE_MQTT_PASSWORD"] == "true" and not mqtt_password:
    invalid.append("MQTT password")
if string_value("CONFIG_IDF_TARGET") != "esp32":
    invalid.append("ESP-IDF target")

if settings.get("CONFIG_IEMP_WEB_SENSOR_INPUT") == "y":
    web_key = string_value("CONFIG_IEMP_WEB_INPUT_KEY")
    if not 8 <= len(web_key) <= 63 or any(not 33 <= ord(char) <= 126 for char in web_key):
        invalid.append("web temperature entry key")

if invalid:
    print("Firmware configuration needs attention: " + ", ".join(invalid))
    raise SystemExit(1)
PY
}

configure_firmware() {
  if $FORCE_CONFIGURE || ! configuration_is_valid false; then
    [[ -t 0 && -t 1 ]] ||
      fail "Firmware configuration is missing or invalid; rerun in an interactive terminal"
    log "Opening firmware configuration; save and exit when the settings are complete"
    (cd "$FIRMWARE_DIR" && idf.py menuconfig)
  else
    log "Reusing validated firmware/sdkconfig"
  fi
}

prompt_mqtt_password() {
  local sdkconfig="${FIRMWARE_DIR}/sdkconfig"

  [[ -f "$sdkconfig" ]] || fail "Firmware configuration was not saved; rerun with --configure"
  # Python reads directly from the terminal, keeping the secret out of shell
  # variables, argv, and the exported environment.
  python3 -c '
import getpass
import json
import os
import re
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
try:
    password = getpass.getpass("Device MQTT password: ")
    confirmation = getpass.getpass("Confirm device MQTT password: ")
except (EOFError, OSError):
    raise SystemExit("Could not read MQTT password from the terminal") from None
if password != confirmation:
    raise SystemExit("MQTT passwords did not match")
if not password or any(not 32 <= ord(char) <= 126 for char in password):
    raise SystemExit("MQTT password must use printable ASCII characters")

contents = path.read_text(encoding="utf-8")
setting = "CONFIG_IEMP_MQTT_PASSWORD=" + json.dumps(password)
contents, count = re.subn(
    r"^CONFIG_IEMP_MQTT_PASSWORD=.*$", lambda match: setting,
    contents, flags=re.MULTILINE,
)
if count == 0:
    contents = contents.rstrip("\n") + "\n" + setting + "\n"

fd, temporary = tempfile.mkstemp(prefix=".sdkconfig-", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        output.write(contents)
    os.replace(temporary, path)
except BaseException:
    os.unlink(temporary)
    raise
' "$sdkconfig" || fail "Could not save MQTT password in firmware/sdkconfig"
  configuration_is_valid || fail "Firmware configuration is incomplete; rerun with --configure"
}

detect_serial_port() {
  local candidate resolved
  local -a candidates=()
  declare -A seen=()

  if [[ -n "$SERIAL_PORT" ]]; then
    [[ -c "$SERIAL_PORT" ]] || fail "Serial port is not a character device: ${SERIAL_PORT}"
    return
  fi

  shopt -s nullglob
  for candidate in /dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*; do
    [[ -e "$candidate" ]] || continue
    resolved="$(readlink -f -- "$candidate")"
    [[ -n "$resolved" && -z "${seen[$resolved]:-}" ]] || continue
    seen[$resolved]=1
    candidates+=("$candidate")
  done
  shopt -u nullglob

  case "${#candidates[@]}" in
    0)
      fail "No USB serial device found; connect the ESP32 or pass --port DEVICE"
      ;;
    1)
      SERIAL_PORT="${candidates[0]}"
      ;;
    *)
      printf '[iemp-firmware] Multiple serial devices found:\n' >&2
      printf '  %s\n' "${candidates[@]}" >&2
      fail "Select the ESP32 with --port DEVICE"
      ;;
  esac
}

verify_serial_access() {
  local port_group
  [[ -r "$SERIAL_PORT" && -w "$SERIAL_PORT" ]] && return
  port_group="$(stat -c '%G' "$SERIAL_PORT" 2>/dev/null || printf 'dialout')"
  fail "No read/write access to ${SERIAL_PORT}. Add ${LOCAL_USER} to the ${port_group} group, log out and back in, then rerun"
}

build_and_flash() {
  log "Compiling the ESP32 firmware"
  (cd "$FIRMWARE_DIR" && idf.py build)

  log "Flashing ${SERIAL_PORT}; do not disconnect power or USB"
  (cd "$FIRMWARE_DIR" && idf.py -p "$SERIAL_PORT" flash)
  log "Firmware compiled and flashed successfully"

  if $MONITOR; then
    log "Opening serial monitor; press Ctrl+] to exit"
    (cd "$FIRMWARE_DIR" && idf.py -p "$SERIAL_PORT" monitor)
  else
    log "Run again with --monitor to view startup logs"
  fi
}

install_host_packages
verify_host_tools
install_esp_idf
configure_firmware
detect_serial_port
verify_serial_access
prompt_mqtt_password
build_and_flash
