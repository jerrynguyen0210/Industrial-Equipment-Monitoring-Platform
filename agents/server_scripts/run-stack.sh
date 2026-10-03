#!/usr/bin/env bash

# Build and run the complete IEMP lab stack on this Linux machine.
set -Eeuo pipefail
umask 077

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly GATEWAY_BIN="${REPO_ROOT}/gateway/build/gateway"
readonly GATEWAY_CONFIG="${REPO_ROOT}/gateway/.env"
readonly RUN_DIR="${REPO_ROOT}/gateway/build/local-run"
readonly PID_FILE="${RUN_DIR}/gateway.pid"
readonly LOG_FILE="${RUN_DIR}/gateway.log"
readonly START_LOCK="${RUN_DIR}/stack-start.lock"

ACTION=start
SKIP_HOST_INSTALL=false
WAIT_TIMEOUT=180
SERVER_ADDRESS=""
ESP32_ADDRESS=""
NETWORK_MODE="prompt"
DOCKER=()

log() { printf '[iemp-stack] %s\n' "$*"; }
fail() { printf '[iemp-stack] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: agents/server_scripts/run-stack.sh [start|stop|status|logs] [options]

Run the complete IEMP lab stack from this checkout on the current Linux machine.
The default action is start.

  start   Install dependencies, build, migrate, seed, and start the local stack.
  stop    Stop the native gateway and Compose services; preserve all data.
  status  Show native gateway and Compose service status.
  logs    Show recent native gateway and Compose logs.

Options for start:
  --skip-host-install      Require dependencies to already be installed.
  --wait-timeout SECONDS   Service startup timeout (default: 180).
  --server-address IPV4    Bind frontend, backend, and MQTT to the server's LAN IP.
  --esp32-address IPV4     Record and validate the ESP32's separate LAN IP.
  --lan-address IPV4       Alias for --server-address.
  --local-only             Bind all server services to 127.0.0.1.
  -h, --help               Show this help.

Without a server address option, an interactive start asks for the server and
ESP32 addresses. Non-interactive starts default to local-only. The ESP32 must
publish to the server address, not to its own address. MQTT and the backend are
not secured for an untrusted network; use LAN mode only in a controlled lab.
EOF
}

if (($# > 0)); then
  case "$1" in
    start | stop | status | logs)
      ACTION="$1"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
  esac
fi

while (($# > 0)); do
  case "$1" in
    --skip-host-install)
      SKIP_HOST_INSTALL=true
      shift
      ;;
    --wait-timeout)
      (($# >= 2)) || fail '--wait-timeout requires a value'
      [[ "$2" =~ ^[1-9][0-9]*$ ]] || fail '--wait-timeout must be a positive integer'
      WAIT_TIMEOUT="$2"
      shift 2
      ;;
    --server-address | --lan-address)
      (($# >= 2)) || fail "$1 requires an IPv4 address"
      [[ "$NETWORK_MODE" == prompt ]] || fail 'Use only one server address mode'
      SERVER_ADDRESS="$2"
      NETWORK_MODE="lan"
      shift 2
      ;;
    --esp32-address)
      (($# >= 2)) || fail '--esp32-address requires an IPv4 address'
      [[ -z "$ESP32_ADDRESS" ]] || fail '--esp32-address may be specified only once'
      ESP32_ADDRESS="$2"
      shift 2
      ;;
    --local-only)
      [[ "$NETWORK_MODE" == prompt ]] || fail 'Use only one server address mode'
      SERVER_ADDRESS="127.0.0.1"
      NETWORK_MODE="local"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1 (use --help)"
      ;;
  esac
done

[[ "$(uname -s)" == Linux ]] || fail 'This launcher requires Linux'
[[ -f "${REPO_ROOT}/compose.yaml" ]] || fail "Cannot find compose.yaml in ${REPO_ROOT}"
[[ -x "${REPO_ROOT}/Setup_Guide/install.sh" ]] || fail 'Setup_Guide/install.sh is missing or not executable'

# A caller's exported values must not override this launcher's selected addresses.
unset FRONTEND_BIND_ADDRESS BACKEND_BIND_ADDRESS MQTT_BIND_ADDRESS

select_docker() {
  command -v docker >/dev/null 2>&1 || fail 'Docker is not installed'
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
    log 'Using sudo to access Docker'
  else
    fail 'Docker is installed, but its daemon is not available'
  fi
}

compose() {
  (cd "$REPO_ROOT" && "${DOCKER[@]}" compose "$@")
}

validate_server_address() {
  IEMP_SERVER_ADDRESS="$1" python3 <<'PY'
import ipaddress
import os
import socket

value = os.environ["IEMP_SERVER_ADDRESS"]
try:
    address = ipaddress.IPv4Address(value)
except ipaddress.AddressValueError:
    raise SystemExit(f"Invalid server IPv4 address: {value}") from None
if address.is_loopback or address.is_multicast or address.is_unspecified:
    raise SystemExit(f"Server address must be a usable non-loopback IPv4 address: {value}")
with socket.socket() as probe:
    try:
        probe.bind((value, 0))
    except OSError as error:
        raise SystemExit(f"Server address is not assigned to this machine: {value} ({error})") from None
PY
}

validate_esp32_address() {
  IEMP_SERVER_ADDRESS="$SERVER_ADDRESS" IEMP_ESP32_ADDRESS="$1" python3 <<'PY'
import ipaddress
import os

server = ipaddress.IPv4Address(os.environ["IEMP_SERVER_ADDRESS"])
value = os.environ["IEMP_ESP32_ADDRESS"]
try:
    address = ipaddress.IPv4Address(value)
except ipaddress.AddressValueError:
    raise SystemExit(f"Invalid ESP32 IPv4 address: {value}") from None
if address.is_loopback or address.is_multicast or address.is_unspecified:
    raise SystemExit(f"ESP32 address must be a usable non-loopback IPv4 address: {value}")
if address == server:
    raise SystemExit("The ESP32 and server must have different IPv4 addresses")
PY
}

choose_network_addresses() {
  local answer default_address entered_address

  case "$NETWORK_MODE" in
    lan)
      validate_server_address "$SERVER_ADDRESS"
      [[ -z "$ESP32_ADDRESS" ]] || validate_esp32_address "$ESP32_ADDRESS"
      ;;
    local)
      [[ -z "$ESP32_ADDRESS" ]] || fail '--esp32-address requires LAN mode'
      ;;
    prompt)
      if [[ ! -t 0 ]]; then
        [[ -z "$ESP32_ADDRESS" ]] || fail '--esp32-address also requires --server-address in non-interactive mode'
        SERVER_ADDRESS="127.0.0.1"
        NETWORK_MODE="local"
        log 'Non-interactive start: using local-only access'
        return
      fi
      read -r -p 'Run frontend, backend, and MQTT on the trusted LAN? [y/N]: ' answer
      case "$answer" in
        y | Y | yes | YES | Yes)
          default_address="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')"
          if [[ -n "$default_address" ]]; then
            read -r -p "Server LAN IPv4 address [${default_address}]: " entered_address
            SERVER_ADDRESS="${entered_address:-$default_address}"
          else
            read -r -p 'Server LAN IPv4 address: ' SERVER_ADDRESS
          fi
          [[ -n "$SERVER_ADDRESS" ]] || fail 'The server LAN IPv4 address is required'
          NETWORK_MODE="lan"
          validate_server_address "$SERVER_ADDRESS"
          if [[ -z "$ESP32_ADDRESS" ]]; then
            read -r -p 'ESP32 LAN IPv4 address (optional): ' ESP32_ADDRESS
          fi
          [[ -z "$ESP32_ADDRESS" ]] || validate_esp32_address "$ESP32_ADDRESS"
          ;;
        n | N | no | NO | No | '')
          [[ -z "$ESP32_ADDRESS" ]] || fail '--esp32-address requires LAN mode'
          SERVER_ADDRESS="127.0.0.1"
          NETWORK_MODE="local"
          ;;
        *)
          fail 'Answer yes or no'
          ;;
      esac
      ;;
  esac
}

configure_bind_addresses() {
  local source_file temporary
  source_file="${REPO_ROOT}/.env"
  [[ -f "$source_file" ]] || source_file="${REPO_ROOT}/.env.example"
  [[ -f "$source_file" ]] || fail 'Neither .env nor .env.example exists'
  temporary="$(mktemp "${REPO_ROOT}/.env.local.XXXXXX")"

  awk -v server_address="$SERVER_ADDRESS" '
    BEGIN {
      frontend = backend = mqtt = 0
    }
    /^FRONTEND_BIND_ADDRESS=/ {
      print "FRONTEND_BIND_ADDRESS=" server_address
      frontend = 1
      next
    }
    /^BACKEND_BIND_ADDRESS=/ {
      print "BACKEND_BIND_ADDRESS=" server_address
      backend = 1
      next
    }
    /^MQTT_BIND_ADDRESS=/ {
      print "MQTT_BIND_ADDRESS=" server_address
      mqtt = 1
      next
    }
    { print }
    END {
      if (!frontend) print "FRONTEND_BIND_ADDRESS=" server_address
      if (!backend) print "BACKEND_BIND_ADDRESS=" server_address
      if (!mqtt) print "MQTT_BIND_ADDRESS=" server_address
    }
  ' "$source_file" > "$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "${REPO_ROOT}/.env"
}

configure_gateway_addresses() {
  local backend_port mqtt_port source_file temporary
  source_file="$GATEWAY_CONFIG"
  [[ -f "$source_file" ]] || fail 'gateway/.env is missing after installation'
  mqtt_port="$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["mosquitto"]["ports"][0]["published"])')"
  backend_port="$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["backend"]["ports"][0]["published"])')"
  temporary="$(mktemp "${REPO_ROOT}/gateway/.env.local.XXXXXX")"

  awk -v server_address="$SERVER_ADDRESS" -v mqtt_port="$mqtt_port" -v backend_port="$backend_port" '
    /^MQTT_HOST=/ { print "MQTT_HOST=" server_address; next }
    /^MQTT_PORT=/ { print "MQTT_PORT=" mqtt_port; next }
    /^API_BASE_URL=/ { print "API_BASE_URL=http://" server_address ":" backend_port "/api"; next }
    { print }
  ' "$source_file" > "$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "$source_file"
}

gateway_pid() {
  local pid
  [[ -s "$PID_FILE" ]] || return 1
  pid="$(<"$PID_FILE")"
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ -r "/proc/${pid}/cmdline" ]] || return 1
  [[ "$(readlink -f -- "/proc/${pid}/exe" 2>/dev/null)" == "$GATEWAY_BIN" ]] || return 1
  tr '\0' '\n' < "/proc/${pid}/cmdline" | grep -Fxq -- "$GATEWAY_CONFIG" || return 1
  printf '%s\n' "$pid"
}

stop_gateway() {
  local pid attempt
  if ! pid="$(gateway_pid)"; then
    rm -f -- "$PID_FILE"
    log 'Gateway is not running'
    return
  fi

  log "Stopping gateway (PID ${pid})"
  kill -TERM "$pid"
  for ((attempt = 0; attempt < 30; attempt++)); do
    if ! gateway_pid >/dev/null; then
      rm -f -- "$PID_FILE"
      return
    fi
    sleep 1
  done
  fail "Gateway did not stop within 30 seconds; inspect ${LOG_FILE}"
}

install_gateway_dependencies() {
  local package
  local -a elevation=()
  local -a missing=()
  local -a packages=(
    cmake g++ libsqlite3-dev libmosquitto-dev libcurl4-openssl-dev nlohmann-json3-dev
  )

  if command -v dpkg-query >/dev/null 2>&1; then
    for package in "${packages[@]}"; do
      if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != 'install ok installed' ]]; then
        missing+=("$package")
      fi
    done
  else
    command -v cmake >/dev/null 2>&1 || fail 'CMake is required to build the gateway'
    command -v g++ >/dev/null 2>&1 || fail 'A C++17 compiler is required to build the gateway'
    return
  fi

  ((${#missing[@]} == 0)) && return
  if $SKIP_HOST_INSTALL; then
    fail "Missing gateway packages: ${missing[*]}. Install them or omit --skip-host-install"
  fi
  command -v apt-get >/dev/null 2>&1 || fail "Install gateway packages: ${missing[*]}"
  if ((EUID != 0)); then
    command -v sudo >/dev/null 2>&1 || fail 'sudo is required to install gateway packages'
    elevation=(sudo)
  fi
  log "Installing gateway packages: ${missing[*]}"
  "${elevation[@]}" apt-get update
  "${elevation[@]}" apt-get install -y "${missing[@]}"
}

build_gateway() {
  [[ -f "$GATEWAY_CONFIG" ]] || fail 'gateway/.env is missing; run start without --skip-host-install'
  stop_gateway
  log 'Building the native gateway on this machine'
  cmake -S "${REPO_ROOT}/gateway" -B "${REPO_ROOT}/gateway/build" \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
  cmake --build "${REPO_ROOT}/gateway/build" --parallel 2
}

start_gateway() {
  local pid attempt
  mkdir -p -- "$RUN_DIR"
  [[ -x "$GATEWAY_BIN" ]] || fail "Gateway executable is missing: ${GATEWAY_BIN}"
  "$GATEWAY_BIN" --config "$GATEWAY_CONFIG" --check-config >/dev/null
  : > "$LOG_FILE"

  log 'Starting the native gateway on this machine'
  nohup "$GATEWAY_BIN" --config "$GATEWAY_CONFIG" 9>&- </dev/null >>"$LOG_FILE" 2>&1 &
  pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"

  for ((attempt = 0; attempt < WAIT_TIMEOUT; attempt++)); do
    if grep -Fq '"event":"subscribed"' "$LOG_FILE"; then
      gateway_pid >/dev/null || fail "Gateway exited after subscribing; inspect ${LOG_FILE}"
      return
    fi
    if ! gateway_pid >/dev/null; then
      tail -n 15 "$LOG_FILE" >&2 || true
      fail "Gateway exited before MQTT subscription; inspect ${LOG_FILE}"
    fi
    sleep 1
  done
  tail -n 15 "$LOG_FILE" >&2 || true
  fail "Gateway did not subscribe within ${WAIT_TIMEOUT} seconds; inspect ${LOG_FILE}"
}

verify_end_to_end() {
  local boot_id attempt
  boot_id="$(python3 -c 'import uuid; print("launcher-" + uuid.uuid4().hex)')"
  log 'Publishing one demo reading and checking PostgreSQL delivery'
  python3 - "$boot_id" <<'PY' | compose exec -T --user 0 mosquitto sh -c \
    'mosquitto_pub -h 127.0.0.1 -u device-demo-001 -P "$(cat /mosquitto/config/auth/device-demo-001.password)" -t equipment/device-demo-001/telemetry -q 1 -s'
import json
import sys

event = {
    "schema_version": 1,
    "device_id": "device-demo-001",
    "boot_id": sys.argv[1],
    "sequence_number": 0,
    "measured_at": None,
    "device_uptime_ms": 1000,
    "metric": "temperature",
    "value": 25.0,
    "unit": "celsius",
    "quality": {"reading": "valid", "clock": "unsynchronised"},
}
sys.stdout.write(json.dumps(event))
PY

  for ((attempt = 0; attempt < WAIT_TIMEOUT; attempt += 2)); do
    if compose exec -T backend python -c '
import sys
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import create_database_engine
from app.db.models import Telemetry

engine = create_database_engine()
with Session(engine) as session:
    found = session.execute(select(Telemetry.id).where(
        Telemetry.device_id == "device-demo-001",
        Telemetry.boot_id == sys.argv[1],
        Telemetry.sequence_number == 0,
    )).scalar_one_or_none()
sys.exit(0 if found is not None else 1)
' "$boot_id" >/dev/null 2>&1; then
      log 'Verified MQTT → local gateway → backend → PostgreSQL'
      return
    fi
    sleep 2
  done
  fail "Demo reading did not reach PostgreSQL within ${WAIT_TIMEOUT} seconds"
}

start_stack() {
  local frontend_port
  local -a installer_args=(--wait-timeout "$WAIT_TIMEOUT")
  command -v flock >/dev/null 2>&1 || fail 'flock is required'
  command -v python3 >/dev/null 2>&1 || fail 'Python 3 is required'
  choose_network_addresses
  mkdir -p -- "$RUN_DIR"
  exec 9>"$START_LOCK"
  flock -n 9 || fail 'Another stack start is already running'

  if $SKIP_HOST_INSTALL; then
    installer_args+=(--skip-host-install)
  fi
  configure_bind_addresses
  "${REPO_ROOT}/Setup_Guide/install.sh" "${installer_args[@]}"
  select_docker
  configure_gateway_addresses
  install_gateway_dependencies
  build_gateway
  start_gateway
  verify_end_to_end
  log 'All local services are running'
  frontend_port="$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["frontend"]["ports"][0]["published"])')"
  log "Dashboard: http://${SERVER_ADDRESS}:${frontend_port}"
  log "Backend API: http://${SERVER_ADDRESS}:$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["backend"]["ports"][0]["published"])')"
  log "ESP32 MQTT setting: ${SERVER_ADDRESS}:$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["mosquitto"]["ports"][0]["published"])')"
  if [[ -n "$ESP32_ADDRESS" ]]; then
    log "ESP32 address: ${ESP32_ADDRESS}"
    log "ESP32 web input page, when enabled: http://${ESP32_ADDRESS}/"
  fi
}

show_status() {
  local result=0 pid
  if pid="$(gateway_pid)"; then
    log "Gateway running (PID ${pid})"
  else
    log 'Gateway not running'
    result=1
  fi
  compose ps --all || result=1
  return "$result"
}

show_logs() {
  if [[ -f "$LOG_FILE" ]]; then
    tail -n 40 "$LOG_FILE"
  else
    log 'Gateway log does not exist'
  fi
  compose logs --tail 40 postgres mosquitto backend frontend
}

case "$ACTION" in
  start)
    start_stack
    ;;
  stop)
    stop_gateway
    select_docker
    compose stop
    ;;
  status)
    select_docker
    show_status
    ;;
  logs)
    select_docker
    show_logs
    ;;
esac
