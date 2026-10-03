# Test the platform on Windows

Run these steps in PowerShell from the repository root. Docker Desktop must use
Linux containers.

## 1. Check Docker

```powershell
docker desktop start --timeout 90
docker version
docker compose version
docker info --format '{{.OSType}}'
docker compose config --quiet
```

`docker version` must show client and server, and OS type must be `linux`. If the
CLI is missing from the current terminal, reopen it or add Docker Desktop's
`resources\bin` directory to `$env:Path`.

## 2. Run the isolated smoke test

```powershell
python -u tests\compose_smoke.py
$LASTEXITCODE
```

Expected exit code is `0`. The test creates a random Compose project and tests
migrations, registry seed, MQTT authentication/ACLs, simulator ingestion,
duplicates, contract edge cases, readiness failures, proxy recovery, and volume
persistence. It removes its own resources and does not use the normal `iemp`
volumes.

## 3. Start a persistent lab stack

```powershell
python infra\mosquitto\provision.py
docker compose up -d --build --wait --wait-timeout 120
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m app.db.seed
docker compose ps
```

Open `http://localhost:8080`. Device Management should show the seeded device and
allow new device registration. Registration automatically creates its MQTT
account; no manual broker script is required.

Verify health and the current migration:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
docker compose exec -T backend python -m alembic current
```

Health should report `ok`, readiness should report `ready` and `database=ok`, and
Alembic should report its current head.

## 4. Run PostgreSQL integration tests

The suite requires a PostgreSQL role allowed to create temporary databases. Use
the dedicated test server described in
[backend/README.md](../backend/README.md#run-the-checks); never point it at a
database containing important data.

## 5. Stop or troubleshoot

```powershell
docker compose logs --tail 100 backend postgres mosquitto frontend
docker compose stop
```

`stop` keeps containers and data. `docker compose down` removes containers and
networks but keeps named volumes. Adding `--volumes` deletes stored database and
broker data.

For port conflicts, set `BACKEND_PORT`, `FRONTEND_PORT`, or `MQTT_PORT` in the
root `.env`. Inspect logs before retrying a failed service.
