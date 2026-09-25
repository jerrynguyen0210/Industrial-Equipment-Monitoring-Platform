# Backend

Telemetry ingestion, persistence, APIs, and equipment monitoring rules.

## Development guide

Read [Backend Coding Conventions](CODING_CONVENTIONS.md) for code structure,
telemetry integrity, API contracts, persistence, security, testing, and operations.

## Setup and validation

The backend uses Python 3.13, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, psycopg,
and PostgreSQL 17.
Runtime and development dependencies are hash-locked in `requirements.txt` and
`requirements-dev.txt`; source pins are in the corresponding `.in` files.

From the repository root, `docker compose up backend` builds this service and
starts its database dependency. Mosquitto is not a backend dependency. The image
runs as UID/GID 10001 and has no application volume or host-source mount.

| Endpoint | Meaning |
| --- | --- |
| `POST /api/v1/telemetry/batches` | Bearer-authenticated batch ingestion; ordered per-item outcomes after commit. |
| `GET /health` | HTTP 200 with `{"status":"ok"}` while the API can serve requests. No dependency check. |
| `GET /ready` | HTTP 200 with `{"status":"ready","database":"ok"}` after an authenticated `SELECT 1`; HTTP 503 with `{"status":"unavailable","database":"unavailable"}` on database failure. |

`/api/health/live` and `/api/health/ready` remain equivalent aliases for existing
clients and the frontend proxy. The [health API contract](../docs/health-api.md)
documents response fields, failure behavior, and machine-checkable examples.
`GET /openapi.json` describes health and the implemented telemetry operation.

Set `DATABASE_URL` to a PostgreSQL URL containing host, database, username, and
password (port defaults to 5432). A nonempty URL takes precedence over `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`; all five `PG*` settings are
required when the URL is empty/unset. Compose supplies the local `PG*` defaults.
Invalid configuration fails startup without printing credentials.
The readiness probe's connection timeout is three seconds; its statement timeout
is two seconds. Readiness reconnects on each request, so a recovered database requires
no API restart. Container health uses readiness; liveness remains independent.

The [minimum registry](../docs/registry.md) persists sites, gateways, and devices
with enabled states, foreign keys, and globally unique device IDs. Alembic owns
schema changes; demo data is inserted only by the explicit seed command below.
The [telemetry storage schema](../docs/telemetry-storage.md) adds all v1 contract
fields, database-generated backend receipt time, UTC timestamps, nullable
measurement time, unique event identity, and device/time indexes.
The [telemetry API validation contract](../docs/telemetry-api-contract.md) supplies
strict request/response models, independent per-item validation, and a generated
[OpenAPI contract with examples](../docs/telemetry-openapi.json). The ingestion route
uses `GATEWAY_CREDENTIALS_JSON` to map registered gateway IDs to unique prototype
bearer tokens. Empty configuration denies all ingestion requests; invalid mappings
fail startup. Credentials are loaded once at startup; restart to rotate/revoke them.
See the [simulator quick start](../simulator/README.md) for a complete runnable slice.
Health responses do not acknowledge telemetry, and readiness checks connectivity only.

## Registry migrations and demo seed

From the repository root, using the backend image and Compose's database settings:

```sh
docker compose up -d --build --wait
docker compose exec backend python -m alembic upgrade head
docker compose exec backend python -m app.seed
docker compose exec backend python -m alembic current
```

This persists `site-demo-001` -> `gateway-demo-001` -> `device-demo-001` in the
PostgreSQL named volume. Repeat seeding preserves names, enabled states, and
existing ownership; a conflicting parent assignment fails and rolls back the
whole seed. Migration and seed are explicit deployment steps, never API startup
side effects. Run migrations once before enabling a registry or telemetry consumer.
The current head is `0002_telemetry`; this adds telemetry to an existing registry
without changing its registrations.

For a native database, export `DATABASE_URL` or all five `PG*` settings into the
shell, then run from `backend/`:

```sh
python -m alembic upgrade head
python -m app.seed
python -m alembic check
```

Alembic and the seed command do not load `.env` automatically. Unlike Uvicorn,
they require exported shell variables. URL precedence and escaping follow the
[configuration guide](../docs/configuration.md). To inspect SQL without connecting:

```sh
python -m alembic upgrade head --sql
```

On a disposable database, `python -m alembic downgrade base` removes telemetry
and registry tables **and their rows**. Back up real data before destructive rollback;
reapplying `upgrade head` recreates an empty schema, not the deleted rows. See the
[registry runbook](../docs/registry.md) for recovery and ownership semantics.
To remove only telemetry on a disposable database, downgrade to `0001_registry`;
see the [telemetry recovery instructions](../docs/telemetry-storage.md#apply-and-recover).

## Development checks

For development checks, create a virtual environment and activate it using your
shell's normal activation command. With Python 3.13+:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements-dev.txt
python -m ruff check --config backend/pyproject.toml backend simulator tests/compose_smoke.py
python -m ruff format --check --config backend/pyproject.toml backend simulator tests/compose_smoke.py
cd backend
python -m unittest discover -s tests -v
```

The [CI workflow](../.github/workflows/local-platform.yml) runs the same lint,
formatting, and unit test commands on Python 3.13 for every push and pull request,
plus the PostgreSQL acceptance suite below.
The pip download cache is keyed by the committed requirements lockfiles; each
run still installs with `--require-hashes`. Unit tests supply their own synthetic
configuration and need no running PostgreSQL. See the [CI guide](../docs/ci.md).

The separate integration suite requires a PostgreSQL test server and a role with
`CREATEDB`. `REGISTRY_TEST_DATABASE_URL` is an explicit maintenance connection;
the suite creates a randomly named database, applies migrations and test data
there, then drops only that database. It never migrates or seeds the maintenance
database and never falls back to the application's `DATABASE_URL`.

```powershell
# From backend/, with a dedicated test server (synthetic local credentials).
$env:REGISTRY_TEST_DATABASE_URL = 'postgresql://registry_test:registry-test-only@127.0.0.1:5432/postgres'
python -m unittest discover -s tests/integration -v
```

For POSIX shells, use `export REGISTRY_TEST_DATABASE_URL='postgresql://...'`.
Missing test configuration fails explicitly. The suite covers up/down/up,
model/migration agreement, duplicate and concurrent device registration,
relationships, required values, disabled ancestors, repeatable/concurrent seed,
conflict rollback, and the actual migration/seed CLI commands. It also checks
telemetry identity uniqueness under concurrent writes, nullable measurement time,
UTC conversion, server-generated receipt time, contract checks, indexed queries,
and telemetry rollback without losing registry data.
HTTP ingestion tests additionally verify ownership, mixed classifications, all
batch boundaries, precise numbers, concurrent retries/conflicts, registry locks,
failed-commit rollback, and lost commit acknowledgement followed by a safe retry.

To run the API natively, install the development dependencies above, then run
from `backend/`. Copy the example once and edit `DATABASE_URL` to match a
separately provisioned local PostgreSQL instance:

```sh
cp .env.example .env
# Edit .env before starting. Existing shell variables take precedence.
uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
```

The Compose database has no published port by default. `python-dotenv` is a
development dependency for Uvicorn's explicit `--env-file` option; the application
does not search for `.env` files. Compose injects settings from the root `.env`
and does not load `backend/.env`. See the [configuration guide](../docs/configuration.md)
for URL escaping, precedence, and secret handling.

To intentionally update dependency locks, use `uv` 0.12.18 from the repository root:

```sh
uv pip compile backend/requirements.in --python-version 3.13 --universal --generate-hashes -o backend/requirements.txt
uv pip compile backend/requirements-dev.in --python-version 3.13 --universal --generate-hashes -o backend/requirements-dev.txt
```

Document API and telemetry contracts in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
