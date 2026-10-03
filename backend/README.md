# Backend

FastAPI service for device registration, telemetry ingestion, PostgreSQL storage,
history, presence, and prototype temperature alerts.

## Application structure

```text
app/
├── main.py                 # Application factory, lifespan, and router composition
├── core/
│   ├── config.py           # Environment configuration
│   ├── gateway_auth.py     # Gateway bearer authentication
│   └── health.py           # Liveness and database readiness
├── db/
│   ├── models.py           # Shared SQLAlchemy models and metadata
│   ├── session.py          # Engine configuration
│   ├── types.py            # UTC database types
│   └── seed.py             # Explicit demo registry seed
├── devices/
│   ├── router.py
│   ├── schemas.py
│   ├── service.py
│   ├── repository.py
│   └── credentials.py      # Device password hashing
├── telemetry/
│   ├── router.py           # Ingestion and device history endpoints
│   ├── schemas.py
│   ├── service.py
│   ├── repository.py
│   ├── validation.py       # Lossless JSON parsing and item classification
│   ├── time.py             # Event-time SQL expression
│   └── openapi.py          # Ingestion contract and schema generation
├── alerts/
│   ├── router.py
│   ├── schemas.py
│   └── service.py          # Episode queries and temperature evaluation
└── integrations/
    └── mqtt.py             # Mosquitto administration
```

Routers handle HTTP input and map service/dependency failures to safe responses.
Schemas define request, response, and validated batch data separately from ORM
models. Device and telemetry services own business rules, sessions, and commit
boundaries; their repositories execute queries without committing. The smaller
alerts feature keeps its episode queries and evaluation in its service.

Telemetry ingestion calls alert evaluation with the same session and device
locks, so readings and alert state commit together. Device registration and
deletion coordinate broker changes with database rollback compensation.
Cross-feature registry and presence queries go through the device repository.
Shared ORM metadata stays in `db/models.py` for Alembic and foreign keys.

Use the feature packages for imports, including `app.db.session` for
`create_database_engine` and `app.db.models` for shared ORM models. Run the demo
seed with `python -m app.db.seed` and generate the ingestion contract with
`python -m app.telemetry.openapi --output PATH`.

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
   docker compose exec -T backend python -m app.db.seed
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
