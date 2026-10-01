#!/usr/bin/env bash

# Install and start the IEMP controlled lab environment.
# Supports 64-bit Raspberry Pi OS, Debian, and Ubuntu. Other Linux
# distributions can use this script after Docker Engine and Compose are installed.

set -Eeuo pipefail
umask 077

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly MIN_COMPOSE_VERSION="2.24.0"
readonly LOCAL_USER="${SUDO_USER:-$(id -un)}"
readonly LOCAL_GROUP="$(id -gn "$LOCAL_USER")"

SKIP_HOST_INSTALL=false
WAIT_TIMEOUT=180
SUDO=()
DOCKER=()

log() {
  printf '[iemp-install] %s\n' "$*"
}

fail() {
  printf '[iemp-install] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: Setup_Guide/install.sh [options]

Install host prerequisites when needed, provision local credentials, build the
Compose services, run database migrations, and seed the demo registry.

Options:
  --skip-host-install      Do not install host packages or Docker.
  --wait-timeout SECONDS  Compose health-check timeout (default: 180).
  -h, --help              Show this help text.

Run this script as your normal user; it invokes sudo only for host installation
and when the current user cannot access the Docker daemon. Existing .env files,
credentials, Compose volumes, and database records are preserved.
EOF
}

while (($# > 0)); do
  case "$1" in
    --skip-host-install)
      SKIP_HOST_INSTALL=true
      shift
      ;;
    --wait-timeout)
      (($# >= 2)) || fail "--wait-timeout requires a value"
      [[ "$2" =~ ^[1-9][0-9]*$ ]] || fail "--wait-timeout must be a positive integer"
      WAIT_TIMEOUT="$2"
      shift 2
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

[[ "$(uname -s)" == "Linux" ]] || fail "This installer supports Linux only"
case "$(uname -m)" in
  x86_64 | aarch64 | arm64) ;;
  *) fail "A 64-bit x86_64 or ARM64 Linux installation is required" ;;
esac

[[ -f "${REPO_ROOT}/compose.yaml" ]] || fail "Cannot find compose.yaml at ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/infra/mosquitto/provision.py" ]] || fail "MQTT provisioner is missing"

if ((EUID != 0)); then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
  fi
fi

version_at_least() {
  local current="$1"
  local required="$2"
  [[ "$(printf '%s\n%s\n' "$required" "$current" | sort -V | head -n 1)" == "$required" ]]
}

compose_version() {
  docker compose version --short 2>/dev/null | sed -E 's/^[^0-9]*([0-9]+\.[0-9]+\.[0-9]+).*/\1/'
}

docker_cli_is_current() {
  local version
  command -v docker >/dev/null 2>&1 || return 1
  version="$(compose_version)"
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  version_at_least "$version" "$MIN_COMPOSE_VERSION"
}

install_debian_host_packages() {
  local docker_distribution codename architecture keyring

  if ((EUID != 0)) && ((${#SUDO[@]} == 0)); then
    fail "sudo or root access is required to install host packages"
  fi

  # shellcheck disable=SC1091
  source /etc/os-release

  case "${ID:-}" in
    ubuntu)
      docker_distribution="ubuntu"
      codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
      ;;
    debian | raspbian)
      docker_distribution="debian"
      codename="${VERSION_CODENAME:-}"
      ;;
    *)
      if [[ " ${ID_LIKE:-} " == *" ubuntu "* ]]; then
        docker_distribution="ubuntu"
        codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
      elif [[ " ${ID_LIKE:-} " == *" debian "* ]]; then
        docker_distribution="debian"
        codename="${VERSION_CODENAME:-}"
      else
        fail "Automatic Docker installation supports Raspberry Pi OS, Debian, and Ubuntu"
      fi
      ;;
  esac
  [[ -n "$codename" ]] || fail "Cannot determine the distribution codename from /etc/os-release"

  log "Installing base host packages"
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y ca-certificates curl git gnupg python3

  if docker_cli_is_current; then
    return
  fi

  log "Configuring Docker's official ${docker_distribution} package repository"
  keyring="/etc/apt/keyrings/docker.asc"
  architecture="$(dpkg --print-architecture)"
  "${SUDO[@]}" install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${docker_distribution}/gpg" |
    "${SUDO[@]}" tee "$keyring" >/dev/null
  "${SUDO[@]}" chmod a+r "$keyring"
  printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: %s\n' \
    "$docker_distribution" "$codename" "$architecture" "$keyring" |
    "${SUDO[@]}" tee /etc/apt/sources.list.d/docker.sources >/dev/null

  "${SUDO[@]}" apt-get update
  if ! "${SUDO[@]}" apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
    fail "Docker installation failed. Remove conflicting distro Docker packages, then rerun this script"
  fi
}

install_host_packages_if_needed() {
  if $SKIP_HOST_INSTALL; then
    log "Skipping host package installation"
    return
  fi

  if command -v python3 >/dev/null 2>&1 && command -v git >/dev/null 2>&1 && docker_cli_is_current; then
    log "Required host tools are already installed"
    return
  fi

  [[ -r /etc/os-release ]] || fail "Cannot identify this Linux distribution"
  if command -v apt-get >/dev/null 2>&1; then
    install_debian_host_packages
  else
    fail "Install Python 3, Git, Docker Engine, and Docker Compose v${MIN_COMPOSE_VERSION}+ for this distribution, then rerun with --skip-host-install"
  fi
}

verify_host_tools() {
  local compose
  command -v python3 >/dev/null 2>&1 || fail "python3 is required"
  command -v git >/dev/null 2>&1 || fail "git is required"
  command -v docker >/dev/null 2>&1 || fail "Docker Engine is required"
  python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 8))' ||
    fail "Python 3.8 or newer is required for installation"

  compose="$(compose_version)"
  [[ "$compose" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "Docker Compose v2 is required"
  version_at_least "$compose" "$MIN_COMPOSE_VERSION" ||
    fail "Docker Compose v${MIN_COMPOSE_VERSION}+ is required (found ${compose})"
}

start_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
    return
  fi

  if command -v systemctl >/dev/null 2>&1; then
    log "Starting Docker Engine"
    "${SUDO[@]}" systemctl enable --now docker >/dev/null 2>&1 || true
  elif command -v service >/dev/null 2>&1; then
    "${SUDO[@]}" service docker start >/dev/null 2>&1 || true
  fi

  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif "${SUDO[@]}" docker info >/dev/null 2>&1; then
    DOCKER=("${SUDO[@]}" docker)
    log "Using sudo for Docker; see Docker's post-install guide for optional non-root access"
  else
    fail "Docker Engine is installed but its daemon is not available"
  fi
}

configure_local_credentials() {
  log "Preparing local API configuration and gateway credential"
  IEMP_REPO_ROOT="$REPO_ROOT" python3 <<'PY'
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

root = Path(os.environ["IEMP_REPO_ROOT"])
root_env = root / ".env"
gateway_env = root / "gateway" / ".env"
token_path = root / "secrets" / "gateway-demo-001.api-token"
gateway_id = "gateway-demo-001"
placeholder = "replace-with-provisioned-gateway-credential"


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def copy_example_if_missing(target: Path, example: Path) -> None:
    if target.exists():
        if not target.is_file():
            raise SystemExit(f"Expected a regular file: {target}")
        return
    atomic_write(target, example.read_text(encoding="utf-8"))


def setting(text: str, name: str):
    match = re.search(rf"^{re.escape(name)}=(.*)$", text, re.MULTILINE)
    return None if match is None else match.group(1).strip()


def replace_setting(path: Path, name: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(name)}=.*$", re.MULTILINE)
    if pattern.search(text) is None:
        raise SystemExit(f"Missing {name} setting in {path}")
    atomic_write(path, pattern.sub(lambda _: f"{name}={value}", text, count=1))


copy_example_if_missing(root_env, root / ".env.example")
copy_example_if_missing(gateway_env, root / "gateway" / ".env.example")

root_text = root_env.read_text(encoding="utf-8")
raw_mapping = setting(root_text, "GATEWAY_CREDENTIALS_JSON")
mapping = {}
if raw_mapping:
    if len(raw_mapping) >= 2 and raw_mapping[0] == raw_mapping[-1] and raw_mapping[0] in "'\"":
        raw_mapping = raw_mapping[1:-1]
    try:
        decoded = json.loads(raw_mapping)
    except (json.JSONDecodeError, TypeError):
        raise SystemExit(f"GATEWAY_CREDENTIALS_JSON in {root_env} is not valid JSON") from None
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in decoded.items()
    ):
        raise SystemExit(f"GATEWAY_CREDENTIALS_JSON in {root_env} must map strings to strings")
    mapping = decoded

gateway_text = gateway_env.read_text(encoding="utf-8")
gateway_value = setting(gateway_text, "GATEWAY_API_KEY")
existing_values = []
if gateway_id in mapping:
    existing_values.append(mapping[gateway_id])
if gateway_value and gateway_value != placeholder:
    existing_values.append(gateway_value)
if token_path.exists():
    if not token_path.is_file():
        raise SystemExit(f"Expected a regular file: {token_path}")
    file_token = token_path.read_text(encoding="utf-8").strip()
    if not file_token:
        raise SystemExit(f"Credential file is empty: {token_path}")
    existing_values.append(file_token)

if len(set(existing_values)) > 1:
    raise SystemExit("Existing gateway API credentials disagree; reconcile them before rerunning")
token = existing_values[0] if existing_values else secrets.token_urlsafe(32)
if not token:
    raise SystemExit("Gateway API credential must not be empty")

if not token_path.exists():
    atomic_write(token_path, token + "\n")
else:
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)

if mapping.get(gateway_id) != token:
    mapping[gateway_id] = token
    compact_mapping = json.dumps(mapping, separators=(",", ":"), ensure_ascii=True)
    replace_setting(root_env, "GATEWAY_CREDENTIALS_JSON", f"'{compact_mapping}'")

if gateway_value in (None, "", placeholder):
    replace_setting(gateway_env, "GATEWAY_API_KEY", token)

os.chmod(root_env, stat.S_IRUSR | stat.S_IWUSR)
os.chmod(gateway_env, stat.S_IRUSR | stat.S_IWUSR)
PY
}

provision_mqtt_credentials() {
  local auth_dir="${REPO_ROOT}/secrets/mosquitto"
  local required=(passwd device-demo-001.password gateway-demo-001.password health.password)
  local file

  if [[ -d "$auth_dir" ]]; then
    for file in "${required[@]}"; do
      [[ -s "${auth_dir}/${file}" ]] || fail "Existing MQTT credential directory is incomplete: ${auth_dir}/${file}"
    done
    log "Reusing existing MQTT credentials"
    return
  fi
  [[ ! -e "$auth_dir" ]] || fail "MQTT credential path is not a directory: ${auth_dir}"

  log "Provisioning MQTT credentials"
  if [[ "${DOCKER[*]}" == "docker" ]]; then
    (cd "$REPO_ROOT" && python3 infra/mosquitto/provision.py)
  else
    (cd "$REPO_ROOT" && "${SUDO[@]}" python3 infra/mosquitto/provision.py)
    "${SUDO[@]}" chown -R "${LOCAL_USER}:${LOCAL_GROUP}" "$auth_dir"
  fi
}

start_platform() {
  cd "$REPO_ROOT"
  log "Validating Compose configuration"
  "${DOCKER[@]}" compose config --quiet

  log "Building and starting the platform (this can take several minutes on a Pi)"
  "${DOCKER[@]}" compose up -d --build --wait --wait-timeout "$WAIT_TIMEOUT"

  log "Applying database migrations and demo registry seed"
  "${DOCKER[@]}" compose exec -T backend python -m alembic upgrade head
  "${DOCKER[@]}" compose exec -T backend python -m app.seed

  log "Verifying API and dashboard health inside the containers"
  "${DOCKER[@]}" compose exec -T backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=10)"
  "${DOCKER[@]}" compose exec -T frontend wget -q -O /dev/null \
    http://127.0.0.1:8080/api/health/ready
  "${DOCKER[@]}" compose ps
}

install_host_packages_if_needed
verify_host_tools
start_docker_daemon
configure_local_credentials
provision_mqtt_credentials
start_platform

frontend_endpoint="$("${DOCKER[@]}" compose config --format json | python3 -c '
import json
import sys
port = json.load(sys.stdin)["services"]["frontend"]["ports"][0]
print("{}:{}".format(port["host_ip"], port["published"]))
')"
backend_endpoint="$("${DOCKER[@]}" compose config --format json | python3 -c '
import json
import sys
port = json.load(sys.stdin)["services"]["backend"]["ports"][0]
print("{}:{}".format(port["host_ip"], port["published"]))
')"
log "Installation complete"
log "Dashboard: http://${frontend_endpoint}"
log "Backend readiness: http://${backend_endpoint}/ready"
log "Credentials were saved locally and were not printed"
log "For ESP32 or remote gateway access, follow Setup_Guide/02-hardware-and-gateway.md"
