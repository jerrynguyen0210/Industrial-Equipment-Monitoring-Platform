# Simulator

`send_batch.py` is a Python 3.13+ standard-library API-mode simulator. It submits
fixed fixtures to `POST /api/v1/telemetry/batches`, checks ordered per-item results,
and reports accepted, duplicate, rejected and unconfirmed counts as JSON.
It bypasses MQTT and the native gateway; MQTT device simulation, gateway queues,
sensor hardware and load generation remain separate work.

## Run the simulator-to-API slice

From the repository root in PowerShell, with Docker running and the repository
virtual environment available, generate a local prototype credential without
printing or committing it:

```powershell
$env:GATEWAY_API_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:GATEWAY_CREDENTIALS_JSON = @{ 'gateway-demo-001' = $env:GATEWAY_API_KEY } | ConvertTo-Json -Compress
docker compose up -d --build --wait
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m app.seed
$env:API_BASE_URL = 'http://127.0.0.1:8000/api'
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/valid-batch.json --expect accepted
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/valid-batch.json --expect duplicate
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/mixed-batch.json --expect 'accepted,rejected:invalid_unit,rejected:unknown_device'
```

For a fresh seeded database, the first call commits one row, replay reports
`duplicate`, and the mixed fixture commits one more row while rejecting the invalid
unit and unregistered device. Verify receipt-time ownership and persisted values:

```powershell
docker compose exec -T postgres psql -U iemp -d iemp -c "SELECT device_id, boot_id, sequence_number, value, measured_at, gateway_received_at, backend_received_at FROM telemetry WHERE boot_id = 'simulator-vertical-slice-v1' ORDER BY sequence_number;"
```

Use your configured PostgreSQL user/database if different from the local defaults.
Fixtures deliberately use fixed historical times and boot IDs for repeatable replay.
On later runs the valid entries are duplicates; use `--expect duplicate` and
`--expect 'duplicate,rejected:invalid_unit,rejected:unknown_device'`, respectively.
To test a new run, copy fixtures and change boot IDs consistently. No randomness,
clock substitution or automatic retries alter a submitted fixture.

`API_BASE_URL` and `GATEWAY_API_KEY` are read from the process environment;
`.env` is not automatically loaded. The key must match a registered, enabled
gateway in backend `GATEWAY_CREDENTIALS_JSON`. For native Uvicorn, export the same
map or use its documented explicit env-file loading. Restart the API after token
rotation/revocation. Keep tokens in ignored local configuration. HTTP redirects
are refused so credentials are sent only to the configured target.

The client sends original fixture bytes, preserving precise JSON numbers and
gateway receipt time. Missing, malformed, contradictory or misordered results are
unconfirmed and exit nonzero. HTTP/network failures also exit nonzero; retain the
fixture unchanged for retry. By default any rejection exits nonzero; `--expect`
allows explicit negative scenarios and requires the exact ordered outcome list.
This small sender accepts event-object fixtures; full malformed-envelope/item
coverage belongs to the backend contract tests. It is not a durable delivery queue.

## Verification

```powershell
# From the repository root, with backend development dependencies installed:
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml simulator
.\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml simulator
Push-Location simulator
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
.\.venv\Scripts\python.exe -u tests/compose_smoke.py
```

The shared smoke suite creates a fresh isolated stack, generates its own token,
runs both fixtures and replay, verifies PostgreSQL rows and receipt times, and
checks persistence across stack restart. CI runs it on every push/pull request.
See [Simulator Coding Conventions](CODING_CONVENTIONS.md) and the
[ingestion contract](../docs/telemetry-api-contract.md).
