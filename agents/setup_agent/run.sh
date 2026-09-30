#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly VENV_DIR="${SCRIPT_DIR}/.venv"

command -v python3 >/dev/null 2>&1 || {
  printf 'python3 is required to start the setup agent\n' >&2
  exit 1
}
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' || {
  printf 'Python 3.10 or newer is required to start the setup agent\n' >&2
  exit 1
}

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

if ! "${VENV_DIR}/bin/python" >/dev/null 2>&1 <<'PY'
import re

import openai

version = re.match(r"^(\d+)\.(\d+)", openai.__version__)
supported = version and (int(version[1]), int(version[2])) >= (3, 22)
raise SystemExit(not supported or int(version[1]) >= 4)
PY
then
  "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check \
    -r "${SCRIPT_DIR}/requirements.txt"
fi

exec "${VENV_DIR}/bin/python" "${SCRIPT_DIR}/setup_agent.py" "$@"
