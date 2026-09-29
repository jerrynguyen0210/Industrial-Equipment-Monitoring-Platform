# Native gateway

The gateway is a C++17 Linux process for Raspberry Pi and other Linux hosts. It
loads an explicit configuration file, validates settings, opens a local SQLite
database in WAL mode with full synchronous durability, subscribes to MQTT
`equipment/+/telemetry` at QoS 1, validates device messages, and persists accepted
messages in a durable SQLite queue. A separate worker posts committed rows to
the backend in batches. It emits JSON logs and stops MQTT, HTTP work, and SQLite
on SIGTERM or SIGINT.

## Build and test

Install a C++17 compiler, CMake 3.16+, SQLite, libmosquitto, and libcurl
development headers, nlohmann JSON headers, Python 3, Mosquitto broker/client
tools for integration tests, and clang-format 18. On Raspberry Pi OS/Debian or
Ubuntu:

```sh
sudo apt-get install cmake g++ libsqlite3-dev libmosquitto-dev libcurl4-openssl-dev nlohmann-json3-dev python3 mosquitto mosquitto-clients clang-format-18
clang-format-18 --dry-run --Werror gateway/src/*.cpp gateway/src/*/*.cpp gateway/include/gateway/*.hpp gateway/include/gateway/*/*.hpp gateway/tests/*.cpp
cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
cmake --build gateway/build --parallel 2
ctest --test-dir gateway/build --output-on-failure
```

Run those commands from the repository root. A production build can omit Python
with `-DBUILD_TESTING=OFF` at configure time. `cmake --install gateway/build
--prefix /usr/local` installs the executable to `/usr/local/bin/gateway`. The CI
gateway job runs the same build and tests on Ubuntu 24.04. The tests check
configuration failures, SIGTERM exit, SQLite migration and restart recovery,
transactional queue claims, authenticated MQTT intake, and HTTP delivery
against a localhost backend stub. They cover mixed backend outcomes, transient
HTTP failure, restart recovery, and malformed responses. They do not establish
delivery against a deployed backend, ESP32 hardware behavior, or power-loss
recovery.

## Configuration and run

Copy [.env.example](.env.example) to an ignored local file such as
`gateway/.env`. Provision the broker credential using
`python infra/mosquitto/provision.py` from the repository root, and replace
`GATEWAY_API_KEY` with a separate token registered in the backend's
`GATEWAY_CREDENTIALS_JSON`. The MQTT credential is used for subscription. The API
credential is sent as a bearer token on each telemetry batch request. Never
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
`gateway_received_at` into SQLite `intake_events` in an explicit transaction.
`gateway_received_at` is captured when the MQTT callback starts, never read from
device JSON. An identical byte-for-byte retry keeps the first payload and time.
A changed payload with the same identity logs `identity_conflict` and leaves the
first row intact. Byte-for-byte comparison is intentionally conservative: a
reformatted but otherwise equivalent JSON retry is also treated as a conflict.

## Durable queue and recovery

`intake_events` has a unique primary key on `(device_id, boot_id,
sequence_number)`. Each new row starts in `pending` with `attempt_count = 0`.
The insert commits before intake logs `message_stored`. The forwarder boundary
reads only SQLite rows; it cannot forward an event directly from an MQTT
callback. The delivery worker atomically claims up to 500 persisted `pending`
rows, changing them to `in_flight` and incrementing `attempt_count`
before any network call. A failed attempt releases the matching claim back to
`pending`. The attempt count measures claims, including attempts stopped before
the request completes. Transactions contain only local database work.

The worker posts `POST /api/v1/telemetry/batches` with the configured bearer
token. It moves the device's `schema_version` into the batch envelope and adds
the original `gateway_received_at` to each event. It copies raw JSON member
text so high precision numbers keep their original representation. Requests are
bounded to 500 rows and 9 MiB, with a 3-second connection and 10-second total
timeout. The worker checks the full ordered response before changing any row:
`accepted` and `duplicate` delete confirmed rows; permanent `rejected` outcomes
move rows with their reason into `quarantined_events` in the same transaction.
Incomplete, mismatched, or unsupported responses leave every row pending.
Transport errors and non-200 responses also keep rows pending. The worker waits
5 seconds after a retryable failure, or 30 seconds after HTTP 401/403; these are
prototype delays without jitter.

On startup, the gateway migrates older `intake_events` tables in place, giving
existing rows `pending` and zero attempts while preserving payloads and original
receipt times. It returns abandoned `in_flight` rows to `pending` without
resetting their attempt counts, reads an initial batch of up to 500 pending
rows, and logs `pending_loaded` with that batch size and the total queue depth.
Later batches remain in SQLite for the worker. Quarantined identities are not
requeued by repeated MQTT delivery. This queue is designed for one gateway
process per database; do not point two running instances at the same
`QUEUE_DB_PATH`.

To back up a queue, stop the service or use Python's SQLite backup API while it
is running. Use a new destination file. For example, with the service stopped:

```sh
python3 -c 'import sqlite3,sys; source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()' /var/lib/iemp-gateway/queue.sqlite3 /safe/location/queue-backup.sqlite3
```

Check a suspect database with `python3 -c 'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print(db.execute("PRAGMA quick_check").fetchone()[0])' /var/lib/iemp-gateway/queue.sqlite3`.
Keep the database and its WAL files for diagnosis if the check fails; there is
no automatic repair path. This prototype has no queue or quarantine capacity
limit, retry jitter, or storage pressure controls yet.

The stored MQTT payload retains its original `schema_version` and device
content. MQTT QoS 1 acknowledges broker delivery, not a gateway SQLite commit;
an event is locally recoverable only after its insert commits. A lost HTTP
response may cause a retry; backend duplicate classification resolves a
previously committed event without changing its identity.

Send SIGTERM to stop the process. The process stops MQTT callbacks, interrupts
and joins the HTTP worker, closes SQLite, logs `stopped`, and exits with status
0. Startup, configuration, and storage errors exit nonzero. Each log line has
UTC `timestamp`, `level`, `component`, `event`, and `message` fields. Credential
values are not logged.
`ready` means the process has started; `subscribed` confirms the broker granted
the QoS 1 telemetry subscription.
The MQTT client currently uses unencrypted TCP with a password; use it only on
the local development host or a controlled lab network. Deployed MQTT TLS
support is still required. Use an HTTPS `API_BASE_URL` for deployed backend
connections; libcurl verifies the server certificate and hostname.

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
| `src/sqlite/` | SQLite connection, schema migration, and durable queue operations. |
| `src/mqtt/` | Authenticated MQTT subscription and callback lifecycle. |
| `src/telemetry/` | Topic and JSON contract validation. |
| `src/intake.cpp` | Gateway receipt timestamp and intake decisions. |
| `src/forwarder.cpp` | Batch construction, response validation, and delivery worker. |
| `src/http/` | libcurl transport with bearer authentication and timeouts. |

The [gateway conventions](CODING_CONVENTIONS.md),
[MQTT topic contract](../docs/mqtt-topic-contract.md), and
[telemetry API contract](../docs/telemetry-api-contract.md) govern the next
reliability and deployment increments.
