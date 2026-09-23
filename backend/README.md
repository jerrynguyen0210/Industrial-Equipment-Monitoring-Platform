# Backend

Telemetry ingestion, persistence, APIs, and equipment monitoring rules.

## Development guide

Read [Backend Coding Conventions](CODING_CONVENTIONS.md) for code structure,
telemetry integrity, API contracts, persistence, security, testing, and operations.

## Setup and validation

The bootstrap uses Python 3.13, FastAPI, Uvicorn, psycopg, and PostgreSQL 17.
Runtime and development dependencies are hash-locked in `requirements.txt` and
`requirements-dev.txt`; source pins are in the corresponding `.in` files.

From the repository root, `docker compose up backend` builds this service and
starts its database dependency. Mosquitto is not a backend dependency. The image
runs as UID/GID 10001 and has no application volume or host-source mount.

| Endpoint | Meaning |
| --- | --- |
| `GET /api/health/live` | HTTP 200 while the API can serve requests. No dependency check. |
| `GET /api/health/ready` | HTTP 200 with `{"status":"ready","database":"ok"}` after an authenticated `SELECT 1`; HTTP 503 if PostgreSQL is unavailable. |

Set `DATABASE_URL` to a PostgreSQL URL containing host, database, username, and
password (port defaults to 5432). A nonempty URL takes precedence over `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`; all five `PG*` settings are
required when the URL is empty/unset. Compose supplies the local `PG*` defaults.
Invalid configuration fails startup without printing credentials.
Connection timeout is three seconds; statement timeout is two
seconds. Readiness reconnects on each request, so a recovered database requires
no API restart. Container health uses readiness; liveness remains independent.

No domain tables, migrations, authentication, or ingestion endpoint are included
in this infrastructure bootstrap. Health responses do not acknowledge telemetry.

For development checks, create a virtual environment and activate it using your
shell's normal activation command. With Python 3.13+:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements-dev.txt
python -m ruff check --config backend/pyproject.toml backend tests/compose_smoke.py
python -m ruff format --check --config backend/pyproject.toml backend tests/compose_smoke.py
cd backend
python -m unittest discover -s tests -v
```

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
