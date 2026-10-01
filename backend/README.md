# Backend

FastAPI service for device registration, telemetry ingestion, PostgreSQL storage,
history, presence, and prototype temperature alerts.

## API summary

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/telemetry/batches` | Authenticated gateway ingestion. |
| `GET/POST /api/v1/devices` | List or register devices. |
| `DELETE /api/v1/devices/{device_id}` | Remove a device without retained history. |
| `POST /api/v1/devices/{device_id}/heartbeat` | Authenticate direct device presence. |
| `POST /api/v1/devices/{device_id}/mqtt` | Provision an older registration in Mosquitto. |
| `GET /api/v1/devices/{device_id}/telemetry` | Bounded temperature history. |
| `GET /api/v1/gateways` | Registration gateway choices. |
| `GET /health`, `GET /ready` | Process liveness and database readiness. |

See [device management](../docs/device-status-api.md),
[ingestion](../docs/telemetry-api-contract.md), and
[health](../docs/health-api.md) for response rules.

## Run with Compose

1. From the repository root, provision and start the stack:

   ```sh
   python3 infra/mosquitto/provision.py
   docker compose up -d --build --wait
   ```

2. Apply migrations and optional demo data:

   ```sh
   docker compose exec -T backend python -m alembic upgrade head
   docker compose exec -T backend python -m app.seed
   docker compose exec -T backend python -m alembic current
   ```

3. Verify:

   ```sh
   curl --fail http://127.0.0.1:8000/health
   curl --fail http://127.0.0.1:8000/ready
   ```

Migrations and seeding are explicit; API startup does neither. The seed creates
the demo site, gateway, and device and must not be used in a customer database.

## Run natively

1. Create and activate a Python 3.13 virtual environment.
2. Install locked development dependencies:

   ```sh
   python -m pip install --require-hashes -r backend/requirements-dev.txt
   ```

3. Copy and edit native settings:

   ```sh
   cp -n backend/.env.example backend/.env
   cd backend
   uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
   ```

The Compose database is not published by default. Native execution needs a
separately reachable PostgreSQL instance. `DATABASE_URL` overrides the five
`PG*` fields. Alembic and the seed do not load `.env`; export their variables.

## Device and gateway credentials

Device registration stores a PBKDF2 hash and updates the Mosquitto password file
and ACL atomically from the API's perspective. A broker failure rolls back the
new database registration. The registration password is used only by that
device's MQTT and heartbeat connections.

Gateway ingestion uses a separate bearer token from `GATEWAY_CREDENTIALS_JSON`.
An empty map denies all ingestion. The backend loads the map at startup, so
rotation requires a restart.

## Run the checks

From the repository root:

```sh
python -m ruff check --config backend/pyproject.toml backend simulator tests
python -m ruff format --check --config backend/pyproject.toml backend simulator tests
cd backend
python -m unittest discover -s tests -v
```

PostgreSQL integration tests require a dedicated maintenance connection whose
role can create databases:

```sh
export REGISTRY_TEST_DATABASE_URL='postgresql://registry_test:password@127.0.0.1:5432/postgres'
cd backend
python -m unittest discover -s tests/integration -v
```

Each suite creates and drops its own randomly named database. It never falls
back to the application `DATABASE_URL`. Do not use an important database as the
maintenance target.

To update locks intentionally, use the repository's documented `uv` version and
regenerate both `requirements.txt` files from their `.in` sources. Follow
[Backend Coding Conventions](CODING_CONVENTIONS.md).
