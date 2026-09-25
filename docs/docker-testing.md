# Test the local platform with Docker Desktop on Windows

Run these commands in PowerShell from the repository root. Start Docker Desktop
and wait for its engine to be running. This project uses Linux containers.

## 1. Check Docker and Compose

The per-user Docker Desktop installation on this workstation is under
`$env:LOCALAPPDATA\Programs\DockerDesktop`. If a terminal opened before installation
cannot find `docker`, add its CLI directory to that terminal's PATH:

```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:Path"
docker desktop start --timeout 90
docker version
docker compose version
docker info --format '{{.OSType}}'
docker compose config --quiet
```

`docker version` must show both Client and Server without a connection error.
The container mode must be `linux`. Compose configuration validation succeeds
with no output and `$LASTEXITCODE` equal to `0`. An all-users installation instead
usually has its CLI in `C:\Program Files\Docker\Docker\resources\bin`.
See Docker's [Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/).

## 2. Run the isolated full-stack smoke test

```powershell
.\.venv\Scripts\python.exe -u tests\compose_smoke.py
$LASTEXITCODE
```

The existing repository virtual environment supplies Python. The smoke script
uses only Python's standard library, so a separate Python 3.13+ installation also
works. The first run downloads images and builds the backend/frontend; it can
take several minutes before the first PASS line.

Expected output includes six PASS lines covering:

- Packaged migration and repeatable registry seed.
- Health checks, frontend proxy, PostgreSQL queries, and MQTT.
- MQTT and frontend availability during a backend outage.
- Database outage and readiness recovery.
- Frontend proxy recovery after backend recreation.
- PostgreSQL/registry and MQTT volume persistence across `down`/`up`.

Success ends with exit code `0`. The script uses a randomly named Compose project,
temporary credentials, and random host ports. It ignores the developer's `.env`
and removes only its own test containers and volumes. Normal `iemp` data is retained.

## 3. Start a persistent demo and inspect the registry

These examples use the committed local defaults (`iemp` user/database). If you
customized PostgreSQL credentials or ports in `.env`, use those values instead.
The current workstation was checked with no root `.env` or shell overrides.

```powershell
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m app.seed
docker compose exec -T backend python -m app.seed
docker compose exec -T backend python -m alembic current
docker compose exec -T backend python -m alembic check
```

All four services should be healthy. The migration revision should be
`0002_telemetry (head)`, and `alembic check` should report no new upgrade operations.
The second seed must succeed without duplicating or re-enabling existing records.

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
docker compose exec -T postgres psql -U iemp -d iemp -c "SELECT s.site_id, g.gateway_id, d.device_id, s.enabled AS site_enabled, g.enabled AS gateway_enabled, d.enabled AS device_enabled FROM sites s JOIN gateways g USING (site_id) JOIN devices d USING (gateway_id);"
```

Expect health `status=ok`, readiness `status=ready` and `database=ok`, and one row:
`site-demo-001` -> `gateway-demo-001` -> `device-demo-001`, with all three enabled
values `t`. Open [the dashboard](http://localhost:8080) to see backend health.
The dashboard currently shows health, not a registry management screen.

## 4. Verify rollback, duplicates, and ownership inside Docker

Keep the persistent demo running, then mount the tests read-only into a temporary
backend container. This uses the backend image's Python and installed runtime
dependencies, so no native PostgreSQL or Python package installation is needed.

```powershell
$registryTests = (Resolve-Path .\backend\tests).Path
docker compose run --rm --no-deps `
  --volume "${registryTests}:/app/tests:ro" `
  --env REGISTRY_TEST_DATABASE_URL=postgresql://iemp:iemp-local-only@postgres:5432/iemp `
  backend python -m unittest discover -s tests/integration -v
```

Expected: the registry and telemetry suites finish with `OK`. They verify
migration up/down/up, duplicate IDs within/across gateways, concurrent registration,
foreign keys, required values, enabled states, seed repeatability/concurrency,
and seed-conflict rollback.
Telemetry checks also cover event identity conflicts/concurrency, UTC timestamps,
nullable measurement time, receipt defaults, and device/time queries.
Each suite creates and removes its own uniquely named database; it does not
downgrade or clear your demo database. The URL above contains only the committed
local defaults.

For a manual duplicate check against the seeded demo:

```powershell
docker compose exec -T postgres psql -U iemp -d iemp -v ON_ERROR_STOP=1 -c "INSERT INTO devices (device_id, gateway_id, name) VALUES ('device-demo-001', 'gateway-demo-001', 'Duplicate test');"
```

The expected result is an error containing `duplicate key value violates unique
constraint "pk_devices"`. This command intentionally returns a nonzero exit code;
the original row remains unchanged. Do not run `alembic downgrade base` against
data you want to retain; the isolated acceptance suite tests rollback safely.

## Stop or troubleshoot

```powershell
docker compose logs --tail 80 backend postgres
docker compose stop
```

`stop` retains containers and database data. To resume, run
`docker compose up -d --wait`. `docker compose down` removes containers/networks
while retaining named volumes. Adding `--volumes` deletes the stored data.

If Docker cannot connect, open Docker Desktop and wait for its engine. If `docker`
is not recognized, use step 1 or reopen the terminal after installation. For a
port conflict, configure `BACKEND_PORT`, `FRONTEND_PORT`, or `MQTT_PORT` in the root
`.env` and use the corresponding address. For a failing container, inspect its
logs before retrying. More details are in the [infrastructure runbook](../infra/README.md).
