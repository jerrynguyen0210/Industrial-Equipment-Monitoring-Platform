# Native gateway

The gateway is a C++17 Linux process for Raspberry Pi and other Linux hosts. It
loads an explicit configuration file, validates settings, opens a local SQLite
database in WAL mode with full synchronous durability, emits JSON lifecycle logs,
and closes SQLite on SIGTERM or SIGINT. The MQTT and HTTP module interfaces are
in `include/gateway/mqtt/` and `include/gateway/http/`; protocol connections,
telemetry intake, queue records, and forwarding are **not implemented yet**. A
running process therefore does not ingest or forward readings.

## Build and test

Install a C++17 compiler, CMake 3.16+, SQLite development headers, Python 3 for
the lifecycle test, and clang-format 18 for the formatting check. On Raspberry Pi
OS/Debian or Ubuntu:

```sh
sudo apt-get install cmake g++ libsqlite3-dev python3 clang-format-18
clang-format-18 --dry-run --Werror gateway/src/*.cpp gateway/src/sqlite/*.cpp gateway/include/gateway/*.hpp gateway/include/gateway/*/*.hpp
cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
cmake --build gateway/build --parallel 2
ctest --test-dir gateway/build --output-on-failure
```

Run those commands from the repository root. A production build can omit Python
with `-DBUILD_TESTING=OFF` at configure time. `cmake --install gateway/build
--prefix /usr/local` installs the executable to `/usr/local/bin/gateway`. The CI
gateway job runs the same build and lifecycle test on Ubuntu 24.04. The test
checks configuration failures, shell override precedence, SIGTERM exit, file
permissions, retained SQLite data, and SQLite integrity after restart. It does
not establish MQTT delivery, HTTP forwarding, or power-loss recovery.

## Configuration and run

Copy [.env.example](.env.example) to an ignored local file such as
`gateway/.env`. Provision the broker credential using
`python infra/mosquitto/provision.py` from the repository root, and replace
`GATEWAY_API_KEY` with a separate token registered in the backend's
`GATEWAY_CREDENTIALS_JSON`. These credentials are validated now but unused until
the protocol clients are implemented. Never place them in version control.

```sh
cp gateway/.env.example gateway/.env
# Edit the token and local addresses.
gateway/build/gateway --config gateway/.env --check-config
gateway/build/gateway --config gateway/.env
```

The config file is required; it is never loaded implicitly. Every supported
setting must be present. Shell environment variables of the same names override
file values. Paths for `MQTT_PASSWORD_FILE` and `QUEUE_DB_PATH` are resolved
relative to the config file's directory unless absolute. The loader accepts
blank lines, full-line `#` comments, unquoted values, and single or double
quoted values. It does not interpolate variables or parse inline comments.
Unknown/duplicate keys, invalid ports or URLs, unreadable password files, and
example API token placeholders fail startup with a setting-specific JSON error.
`--check-config` validates settings without opening or creating SQLite.

Put `QUEUE_DB_PATH` on persistent local storage whose parent directory is
writable by the service account. Newly created database and WAL files use
owner-only permissions. Existing file permissions are not changed. A missing
parent directory causes a clear storage error at startup.

Send SIGTERM to stop the process. The process waits for the signal, closes its
SQLite handle, logs `stopped`, and exits with status 0. Startup/configuration and
storage errors exit nonzero. Each log line has UTC `timestamp`, `level`,
`component`, `event`, and `message` fields. Credential values are not logged.

For systemd, see [gateway.service.example](gateway.service.example). Create the
`iemp-gateway` service account, install the config at
`/etc/iemp-gateway/gateway.env` readable only by that account, and make
`MQTT_PASSWORD_FILE` an absolute path readable by it. The unit creates
`/var/lib/iemp-gateway` and overrides `QUEUE_DB_PATH` to place the database
there. Adjust paths and account names for the host. `systemctl stop` sends
SIGTERM and waits for the normal close path.

## Module boundaries

| Directory | Responsibility |
| --- | --- |
| `src/config.cpp` | Load and validate process settings. |
| `src/log.cpp` | JSON lifecycle and error logs. |
| `src/sqlite/` | SQLite connection ownership, WAL and durability setup. |
| `include/gateway/mqtt/` | Future authenticated subscription boundary. |
| `include/gateway/http/` | Future batch submission boundary. |

The [gateway conventions](CODING_CONVENTIONS.md),
[MQTT topic contract](../docs/mqtt-topic-contract.md), and
[telemetry API contract](../docs/telemetry-api-contract.md) govern the next
protocol and durable-queue increments.
