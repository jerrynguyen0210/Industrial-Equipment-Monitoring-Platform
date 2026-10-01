#!/usr/bin/env bash

# Keep the original setup-guide command working.
set -Eeuo pipefail
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec "${SCRIPT_DIR}/../agents/hardware_script/compile-and-flash-esp32.sh" "$@"
