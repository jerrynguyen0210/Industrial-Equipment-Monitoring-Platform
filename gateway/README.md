# Native gateway

C++17 Linux service that subscribes to MQTT, validates device events, commits
them to a durable SQLite queue, and forwards HTTP batches to the backend.

## Build and test

1. If the Compose broker uses port 1883 on this host, stop it before installing
   native Mosquitto; the package may start its own broker service:

   ```sh
   docker compose stop mosquitto
   ```

2. Install dependencies on Raspberry Pi OS, Debian, or Ubuntu:

   ```sh
   sudo apt-get install cmake g++ libsqlite3-dev libmosquitto-dev \
     libcurl4-openssl-dev nlohmann-json3-dev python3 mosquitto \
     mosquitto-clients clang-format-18
   sudo systemctl disable --now mosquitto
   ```

   On a host without systemd, omit the last command. Restart the Compose broker
   with `docker compose up -d --wait mosquitto`.

3. From the repository root, run:

   ```sh
   clang-format-18 --dry-run --Werror gateway/src/*.cpp gateway/src/*/*.cpp \
     gateway/include/gateway/*.hpp gateway/include/gateway/*/*.hpp gateway/tests/*.cpp
   cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
   cmake --build gateway/build --parallel 2
   ctest --test-dir gateway/build --output-on-failure
   ```

The tests cover config errors, shutdown, SQLite recovery, MQTT intake, HTTP
outcomes, retries, and backend recovery. Hardware and real power loss need
separate tests.

## Configure and run

1. Copy the example and edit local addresses/token:

   ```sh
   cp -n gateway/.env.example gateway/.env
   chmod 600 gateway/.env
   ```

2. Keep `MQTT_PASSWORD_FILE` pointed at the gateway subscriber password. Set
   `GATEWAY_API_KEY` to the separate token in backend
   `GATEWAY_CREDENTIALS_JSON`. Put `QUEUE_DB_PATH` on persistent writable storage.
3. Validate and run:

   ```sh
   gateway/build/gateway --config gateway/.env --check-config
   gateway/build/gateway --config gateway/.env
   ```

The config path is always explicit. Environment variables override matching
file entries. Relative secret and queue paths start at the config directory.
Invalid, unknown, or duplicate settings fail before storage opens.

## Intake and queue behavior

The gateway accepts one non-retained schema v1 JSON event on
`equipment/{device_id}/telemetry`. It rejects oversized messages, duplicate JSON
keys, unknown fields, gateway-owned fields, bad types, and topic/payload ID
mismatch without logging the payload.

For a new `(device_id, boot_id, sequence_number)`, it commits the original JSON
bytes and its own UTC receipt time before logging `message_stored`. An identical
byte replay keeps the first row. Changed bytes with the same identity are
quarantined as a conflict.

The worker claims up to 500 rows, then posts a batch with three-second connect
and ten-second total timeouts. `accepted` and `duplicate` rows are deleted;
permanent rejections move to `quarantined_events`. Transport errors, non-200
responses, and malformed/incomplete results return all claimed rows to pending.
Retries use jittered exponential delay capped at 30 seconds.

SQLite uses WAL mode and full synchronous durability. On startup, abandoned
`in_flight` rows return to pending. One gateway process must own each queue file.
There is currently no queue/quarantine capacity limit.

Complex delivery boundary:

```text
MQTT PUBACK -> broker receipt
message_stored -> SQLite commit
batch_applied -> backend returned committed item outcomes
```

Only the later boundary includes the earlier work.

## Demonstrate outage recovery

```sh
python3 gateway/tests/demo_backend_outage.py \
  --gateway gateway/build/gateway --outage-seconds 60
```

The script creates an isolated stack, publishes during a backend outage, checks
automatic queue drain and unique PostgreSQL rows, then removes its resources.

## Install as a service

1. Install the binary and create a service account:

   ```sh
   sudo cmake --install gateway/build --prefix /usr/local
   sudo useradd --system --home /var/lib/iemp-gateway \
     --shell /usr/sbin/nologin iemp-gateway
   sudo install -d -m 0700 -o iemp-gateway -g iemp-gateway /etc/iemp-gateway
   ```

2. Install the private config and MQTT password under `/etc/iemp-gateway/`, owned
   by the service account with mode 0600.
3. Set an absolute password path and reachable MQTT/API addresses in the config.
4. Install and start the unit:

   ```sh
   sudo install -m 0644 gateway/gateway.service.example \
     /etc/systemd/system/iemp-gateway.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now iemp-gateway
   journalctl -u iemp-gateway -f
   ```

Skip `useradd` when the account already exists. The unit stores the queue under
`/var/lib/iemp-gateway`.

## Back up and check the queue

Stop the service, then create a new SQLite backup file:

```sh
python3 -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()' \
  /var/lib/iemp-gateway/queue.sqlite3 /safe/location/queue-backup.sqlite3
```

Check integrity:

```sh
python3 -c 'import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); print(d.execute("PRAGMA quick_check").fetchone()[0])' \
  /var/lib/iemp-gateway/queue.sqlite3
```

Keep a failed database and its WAL files for diagnosis. No automatic repair path
exists. See [Gateway Coding Conventions](CODING_CONVENTIONS.md).
