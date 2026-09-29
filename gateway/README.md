# Native gateway

The gateway is a C++17 Linux process for Raspberry Pi and other Linux hosts. It
loads an explicit configuration file, validates settings, opens a local SQLite
database in WAL mode with full synchronous durability, subscribes to MQTT
`equipment/+/telemetry` at QoS 1, validates device messages, and persists accepted
messages. It emits JSON logs and closes MQTT and SQLite on SIGTERM or SIGINT.
HTTP batch forwarding is **not implemented yet**; stored readings do not reach the
backend through this process.

## Build and test

Install a C++17 compiler, CMake 3.16+, SQLite and libmosquitto development
headers, nlohmann JSON headers, Python 3, Mosquitto broker/client tools for the
integration test, and clang-format 18. On Raspberry Pi OS/Debian or Ubuntu:

```sh
sudo apt-get install cmake g++ libsqlite3-dev libmosquitto-dev nlohmann-json3-dev python3 mosquitto mosquitto-clients clang-format-18
clang-format-18 --dry-run --Werror gateway/src/*.cpp gateway/src/*/*.cpp gateway/include/gateway/*.hpp gateway/include/gateway/*/*.hpp
cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
cmake --build gateway/build --parallel 2
ctest --test-dir gateway/build --output-on-failure
```

Run those commands from the repository root. A production build can omit Python
with `-DBUILD_TESTING=OFF` at configure time. `cmake --install gateway/build
--prefix /usr/local` installs the executable to `/usr/local/bin/gateway`. The CI
gateway job runs the same build and tests on Ubuntu 24.04. The tests check
configuration failures, SIGTERM exit, SQLite integrity, and authenticated MQTT
intake against a temporary broker with topic ACLs. They cover valid, malformed,
duplicate, conflicting, and forged messages. They do not establish HTTP
forwarding, ESP32 hardware behavior, or power-loss recovery.

## Configuration and run

Copy [.env.example](.env.example) to an ignored local file such as
`gateway/.env`. Provision the broker credential using
`python infra/mosquitto/provision.py` from the repository root, and replace
`GATEWAY_API_KEY` with a separate token registered in the backend's
`GATEWAY_CREDENTIALS_JSON`. The MQTT credential is used for subscription. The API
credential is validated but unused until HTTP forwarding is implemented. Never
place either credential in version control.

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

## MQTT intake and receipt semantics

The gateway subscribes at QoS 1 and validates one JSON object per message. It
requires schema version 1, the documented event and quality fields and types,
finite numeric `value`, and a `device_id` matching the topic. It rejects unknown
fields, duplicate JSON keys, retained messages, payloads over 16 KiB, and
messages that contain `gateway_received_at` or other gateway-owned fields.
Rejections log a safe reason without the payload.

On the first valid delivery for `(device_id, boot_id, sequence_number)`, the
gateway writes the **original MQTT JSON bytes** and its own UTC
`gateway_received_at` into SQLite `intake_events` in one autocommit insert.
`gateway_received_at` is captured when the MQTT callback starts, never read from
device JSON. An identical byte-for-byte retry keeps the first payload and time.
A changed payload with the same identity logs `identity_conflict` and leaves the
first row intact. Byte-for-byte comparison is intentionally conservative: a
reformatted but otherwise equivalent JSON retry is also treated as a conflict.

The stored MQTT payload still contains `schema_version`; future HTTP forwarding
must validate and transform it for the backend contract without changing device
content or the original receipt time. The intake table is not yet capacity
bounded. MQTT QoS 1 acknowledges broker delivery, not a gateway SQLite commit;
an event is locally recoverable only after its insert commits. Do not treat this
increment as an end-to-end delivery guarantee.

Send SIGTERM to stop the process. The process stops MQTT callbacks, closes its
SQLite handle, logs `stopped`, and exits with status 0. Startup/configuration and
storage errors exit nonzero. Each log line has UTC `timestamp`, `level`,
`component`, `event`, and `message` fields. Credential values are not logged.
`ready` means the process has started; `subscribed` confirms the broker granted
the QoS 1 telemetry subscription.
The MQTT client currently uses unencrypted TCP with a password; use it only on
the local development host or a controlled lab network. Deployed TLS support is
still required.

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
| `src/sqlite/` | SQLite connection ownership, WAL setup, and intake rows. |
| `src/mqtt/` | Authenticated MQTT subscription and callback lifecycle. |
| `src/telemetry/` | Topic and JSON contract validation. |
| `src/intake.cpp` | Gateway receipt timestamp and intake decisions. |
| `include/gateway/http/` | Future batch submission boundary. |

The [gateway conventions](CODING_CONVENTIONS.md),
[MQTT topic contract](../docs/mqtt-topic-contract.md), and
[telemetry API contract](../docs/telemetry-api-contract.md) govern the next
protocol and durable-queue increments.
