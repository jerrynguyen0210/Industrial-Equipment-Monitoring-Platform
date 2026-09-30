# Customer evaluation deployment guide — version01

This guide installs and validates `version01` as a supervised evaluation. It is
not a production deployment procedure. Use only synthetic data or dedicated test
equipment on a trusted, isolated network. Do not use the platform for equipment
control or safety alarms.

## 1. Confirm scope and prerequisites

Before starting, name a customer test owner and agree on the test window,
evaluation host, allowed test data, network boundary, and stop/rollback owner.
Do not continue if the host is internet-facing or the evaluation requires user
authentication, MQTT TLS, production data, or unattended operation.

The supported automated path requires:

- A 64-bit Raspberry Pi OS, Debian, or Ubuntu host (`x86_64`, `aarch64`, or
  `arm64`).
- At least 2 GB RAM plus build overhead and sufficient free disk space.
- Internet access during the first build.
- Docker Engine and Docker Compose v2.24 or newer. The installer can install
  them on supported Debian-family hosts when run by a sudo-capable user.
- Python 3.8 or newer for installation. Python 3.13 or newer is required only
  for the full isolated smoke test.
- Host ports 8080, 8000, and 1883 free on loopback.

The release intentionally binds all published ports to `127.0.0.1`. For a
remote browser, keep that setting and use an SSH tunnel from an authorized
workstation:

```sh
ssh -L 8080:127.0.0.1:8080 user@evaluation-host
```

Then open `http://127.0.0.1:8080` on that workstation. Do not change bind
addresses to `0.0.0.0`; this prototype has no dashboard access control.

## 2. Transfer and verify

Transfer both `iemp-version01.tar.gz` and `iemp-version01.tar.gz.sha256` to the
evaluation host. Verify the archive before extracting it:

```sh
sha256sum -c iemp-version01.tar.gz.sha256
tar -xzf iemp-version01.tar.gz
cd version01
sha256sum -c SHA256SUMS
```

Both checks must report `OK`. Stop and obtain a clean copy if a checksum fails.
The package contains no provisioned `.env` files, passwords, API tokens, gateway
queue database, PostgreSQL volume, or firmware configuration.

Record the release metadata before deployment:

```sh
cat VERSION
docker version
docker compose version
python3 --version
```

## 3. Install the evaluation stack

Run the installer as the normal login user from the extracted package root:

```sh
./Setup_Guide/install.sh --wait-timeout 300
```

The script installs missing host prerequisites where supported, creates unique
local MQTT passwords and a gateway API token, builds and starts PostgreSQL,
Mosquitto, the backend, and frontend, applies all database migrations, seeds the
three demo identities, and verifies health. Generated secrets remain in ignored
local files and are not printed.

If Docker, Compose, Git, and Python are already managed by customer IT, use:

```sh
./Setup_Guide/install.sh --skip-host-install --wait-timeout 300
```

The installer is safe to rerun: it validates and reuses existing configuration,
credentials, named volumes, and database records. Never email, commit, or paste
the generated `.env`, `gateway/.env`, or `secrets/` contents into a ticket.

## 4. Verify service health

```sh
docker compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8080/api/health/ready
docker compose exec -T backend python -m alembic current
```

All four services must be healthy. Liveness returns `{"status":"ok"}`;
readiness returns `{"status":"ready","database":"ok"}`; and Alembic reports
`0004_temperature_alerts (head)`.

If any command fails, collect the diagnostic bundle in section 8 and stop the
acceptance test until the cause is understood.

## 5. Run the synthetic acceptance test

Load the generated gateway token into the current shell without printing it,
then send six unique deterministic readings through the HTTP ingestion path:

```sh
export GATEWAY_API_KEY="$(tr -d '\r\n' < secrets/gateway-demo-001.api-token)"
export API_BASE_URL=http://127.0.0.1:8000/api
python3 simulator/simulate.py \
  --device-id device-demo-001 \
  --run-id "customer-eval-$(date -u +%Y%m%dT%H%M%SZ)" \
  --start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --profile ramp --temperature 24 --step 0.5 \
  --interval-ms 1000 --count 6 --batch-size 3 --mode http --fast
unset GATEWAY_API_KEY API_BASE_URL
```

The JSON summary must show six attempted/sent confirmations, no unconfirmed
events, no unsent events, and only accepted outcomes. Open:

- Overview: `http://127.0.0.1:8080/`
- History: `http://127.0.0.1:8080/history`
- Service status: `http://127.0.0.1:8080/status`

Confirm `device-demo-001` and its recent readings appear. Then verify persistence
through a normal restart:

```sh
docker compose stop
docker compose up -d --wait --wait-timeout 300
curl --fail http://127.0.0.1:8080/api/health/ready
docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT device_id, COUNT(*) AS readings FROM telemetry GROUP BY device_id ORDER BY device_id"'
```

The stack must return to healthy state and the telemetry count must not decrease.
Record command output and screenshots as evaluation evidence. This baseline
test bypasses the native gateway; it validates the Compose platform, API,
database, persistence, and dashboard.

## 6. Optional gateway and hardware test

Only continue if the customer approved plaintext MQTT inside the isolated test
network and test hardware is available. Follow
[Setup_Guide/02-hardware-and-gateway.md](Setup_Guide/02-hardware-and-gateway.md)
to build the native gateway, install its service, configure an ESP32, and verify
the complete device → MQTT → SQLite → HTTP → PostgreSQL path.

Keep `firmware/sdkconfig`, firmware images, MQTT passwords, API tokens, and the
gateway SQLite queue private. A synthetic or web-entry firmware mode must use a
separate demo identity and must not be reported as physical-sensor evidence.

For a more extensive software-only test on a host with Python 3.13+, run:

```sh
python3 tests/compose_smoke.py
```

This creates an isolated temporary Compose project, exercises authentication,
ingestion, outages, recovery, and persistence, and removes only its own test
resources.

## 7. Acceptance criteria

The controlled evaluation passes only when all applicable items are recorded:

- Archive and extracted-file checksums pass.
- Release `VERSION`, host details, test owner, and test time are recorded.
- All four Compose services report healthy.
- Backend and proxied readiness checks pass.
- Alembic is at `0004_temperature_alerts (head)`.
- Six synthetic events are accepted and visible in History.
- A stop/start cycle preserves the readings and restores healthy status.
- If hardware is in scope, probe disconnect, valid temperature, MQTT intake,
  gateway queue, backend storage, and recovery evidence are captured.
- The customer acknowledges the limitations in `RELEASE_NOTES.md` and no
  production/sensitive data was used.

## 8. Troubleshooting and support bundle

First inspect local status and logs:

```sh
docker compose ps --all
docker compose logs --no-color --tail 200 postgres mosquitto backend frontend > version01-support.log
docker compose config --quiet
df -h
```

Review `version01-support.log` before sharing it. The application is designed not
to log credential values, but customer policy still governs diagnostic data.
Do not attach `.env`, `gateway/.env`, anything under `secrets/`, firmware build
configuration, gateway queue files, database dumps, or raw customer telemetry.

Common checks and operating procedures are in
[Setup_Guide/03-operations.md](Setup_Guide/03-operations.md). Record the exact
failing command, UTC time, host architecture, Docker/Compose versions, release
metadata, service status, and sanitized log excerpt for support.

## 9. Stop, rollback, and retain evidence

To stop the evaluation without deleting data:

```sh
docker compose stop
```

To remove its containers and network while retaining named volumes:

```sh
docker compose down
```

Do not add `--volumes`: that deletes stored PostgreSQL and Mosquitto data. Before
any upgrade or removal, follow the backup procedure in
[Setup_Guide/03-operations.md](Setup_Guide/03-operations.md) and preserve the
release archive, `VERSION`, checksum results, evaluation evidence, approved
configuration, and credentials in customer-controlled storage.

Because this is the initial packaged version, rollback means stopping version01
and restoring the customer's pre-evaluation host state under the agreed change
plan. Do not attempt a database migration downgrade on data that must be kept.
