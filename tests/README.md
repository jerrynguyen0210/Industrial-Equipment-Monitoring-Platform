# Shared Tests

Tests and fixtures that validate integration across workstreams.

## Development guide

Read [Shared Testing Coding Conventions](CODING_CONVENTIONS.md) for suite placement,
fixtures, contract verification, reliability scenarios, and acceptance evidence.

## Telemetry contract edge cases

[telemetry_scenarios.py](telemetry_scenarios.py) exercises the authenticated backend
API using the versioned [scenario catalog](fixtures/telemetry-scenarios.json).
It uses Python 3.13+ and only the standard library. All eight cases run by default;
each case includes its own setup requests and can run independently.

Expected outcomes follow the [ingestion contract](../docs/telemetry-api-contract.md)
and approved F02-F05 examples. Every request expects HTTP 200 and one ordered
result per input, including all-rejected batches. A request-level error, incomplete
response, identity mismatch, or unexpected outcome fails the run.

| Scenario / CLI name | Requests and exact expected outcomes | Stored rows |
| --- | --- | --- |
| `duplicate` | Original: `accepted`; identical retry: `duplicate`. | 1 |
| `identity-conflict` | Original: `accepted`; same identity with value 99: `rejected:identity_conflict`; original retry: `duplicate`. | 1, original content |
| `invalid-unit` | Fahrenheit: `rejected:invalid_unit`. | 0 |
| `malformed-value` | String, boolean, null, string `NaN`, array and object: each `rejected:malformed_value`. | 0 |
| `unknown-device` | Unregistered device: `rejected:unknown_device`. | 0 |
| `stale-timestamp` | Measurement from `2000-01-01T00:00:00Z`: `accepted`. | 1, historical time preserved |
| `out-of-order-sequence` | Sequence 12 first: `accepted`; then 10 and 11: `accepted, accepted`. | 3 |
| `mixed-batch` | Setup: `accepted`; mixed: `accepted, duplicate, rejected:identity_conflict, rejected:invalid_unit, rejected:malformed_value, rejected:unknown_device, accepted`. | 3 |

Stale and out-of-order readings are accepted for storage: the ingestion contract
does not define an age cutoff or require monotonically arriving sequences.
These fixtures make no claims about live alerts, online status, cross-boot ordering,
gateway queues, or hardware. Literal JSON `NaN` is a request-level malformed batch;
the malformed-value scenario deliberately uses valid JSON to test item rejections.

### Generate or list without services

From the repository root in PowerShell (or use `python` with the venv activated):

```powershell
.\.venv\Scripts\python.exe tests/telemetry_scenarios.py --list
.\.venv\Scripts\python.exe tests/telemetry_scenarios.py --export-only --run-id review-01
```

The catalog contains a base event and shallow per-event overrides. Generation
expands these into standalone `schema_version/events` JSON requests, plus
`expected.json` listing the exact outcome arrays and execution order. No fixture
metadata is sent on the wire. Files go to ignored `test-results/telemetry/<run-id>/`;
`--output-dir` changes the parent directory. Existing run directories are never
overwritten. Generation alone does not report a passing backend test.

The same run ID, selected cases, and device ID produce identical request bytes.
Each case has a separate `qa-<run-id>-<scenario>` boot ID. All timestamps are fixed;
the generator never substitutes the current time. Replaying a fixture preserves
its original identity, value, quality and gateway receipt time.

### Run against a dedicated test backend

Use the [simulator setup](../simulator/README.md#run-the-simulator-to-api-slice) to
configure a gateway credential, apply migrations and explicitly seed the registry.
The enabled gateway and its site must own the enabled `device-demo-001`, or pass
`--device-id` for a dedicated registered device. Keep
`qa-unknown-<run-id>` unregistered. The runner does not seed or modify the registry.

```powershell
# API_BASE_URL includes /api. The token must match the backend's runtime map.
$env:API_BASE_URL = 'http://127.0.0.1:8000/api'
# Set GATEWAY_API_KEY to the provisioned test token in this shell.
.\.venv\Scripts\python.exe tests/telemetry_scenarios.py
.\.venv\Scripts\python.exe tests/telemetry_scenarios.py --scenario identity-conflict
.\.venv\Scripts\python.exe tests/telemetry_scenarios.py --scenario stale-timestamp --scenario out-of-order-sequence
$LASTEXITCODE
```

`--scenario` accepts any name in the table and can be repeated. Without `--run-id`,
each invocation generates and reports a fresh UUID namespace, so repeated and
concurrent runs do not collide. An explicit run ID must be unused in the target
database for a fresh run's `accepted` expectations to hold. Supply
`--api-base-url` to override the environment and `--timeout` to change the finite
per-request timeout (default 10 seconds). `.env` files are not loaded.
Credentials are read only from `GATEWAY_API_KEY`; redirects are refused.

The runner exports request files before sending them. It prints a JSON summary
and saves `report.json` alongside them, with expected/actual ordered outcomes,
HTTP status, server batch IDs, skipped steps and overall pass/fail. Exit codes:
`0` all expectations met (or successful list/export), `1` HTTP/response/outcome
failure, `2` invalid configuration or export failure. After a failed step, dependent
steps in that scenario are skipped; independent cases continue. There are no
automatic retries. Fixture and report files contain no gateway credential.

For deliberate replay, use the exported request with the existing sender:

```powershell
.\.venv\Scripts\python.exe simulator/send_batch.py --batch test-results/telemetry/review-01/duplicate-01-original.json --expect accepted
.\.venv\Scripts\python.exe simulator/send_batch.py --batch test-results/telemetry/review-01/duplicate-02-retry.json --expect duplicate
```

The standalone runner checks HTTP outcomes and leaves accepted telemetry in the
dedicated backend for inspection; it does not delete data. The isolated Compose
suite below verifies all nine expected rows field by field, rejected-item absence,
original content after conflicts, historical times, and persistence across restart,
then removes only its own stack and volumes. No SQL access is required by the CLI.

Run the fixture/CLI checks without Docker:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

These checks use a loopback HTTP stub to verify CLI behavior, exact request bytes,
negative assertions and failure reporting; backend evidence comes from Compose.
Full end-to-end monitoring workflows remain future work. Workstream unit tests
belong with the implementation they exercise.

## Setup and validation

The local-platform smoke suite uses Python 3.13+ standard-library tools and Docker
Compose v2.24+.

For Windows PowerShell, see the [step-by-step Docker testing guide](../docs/docker-testing.md),
including Docker CLI discovery and running registry tests inside the backend image.

From the repository root with Docker running:

```sh
docker compose config --quiet
python tests/compose_smoke.py
```

The suite creates an isolated `iemp-smoke-<random>` project, ignores the developer's
`.env`, selects ephemeral loopback ports, and builds the actual application images.
It verifies:

- All service health checks pass, backend `/health` and `/ready` return the
  documented JSON, and the frontend can reach `/api/health/ready` through its
  same-origin proxy.
- PostgreSQL queries, MQTT publish/subscribe, and the published host MQTT port work.
- The backend image can apply its Alembic migration and run the registry seed
  twice, producing the expected enabled site/gateway/device hierarchy.
- The API-mode simulator submits a valid batch, matching replay and mixed batch,
  and verifies independent outcomes plus database-generated receipt times.
- The QA runner exercises all eight contract edge cases over HTTP, and PostgreSQL
  contains exactly the expected identities and values, with rejected items absent.
- Generated ramp events span three boots, preserve expected values and counters
  in PostgreSQL, replay as duplicates, and survive stack restart.
- Mosquitto and frontend remain available while the backend is stopped.
- Database failure returns readiness HTTP 503 with structured JSON through both
  the backend and frontend proxy while `/health` remains 200, and readiness
  recovers after PostgreSQL returns.
- The frontend proxy recovers after backend container recreation.
- SQL data, seeded registry, ingested telemetry, and MQTT messages survive `down` followed
  by `up`.

Cleanup removes only the generated project's containers, networks, and test
volumes, including on ordinary failures. Abruptly killing Python can leave a test
project behind; inspect `docker compose ls --all` and use its exact generated
project name when cleaning it up. No hardware or native gateway is exercised.
This covers infrastructure and the API ingestion slice; gateway queue durability
and full MVP acceptance require additional scenarios.

Registry migration/constraint acceptance tests live in
[`backend/tests/integration/`](../backend/tests/integration/test_registry.py).
They use an explicit `REGISTRY_TEST_DATABASE_URL`, create a separate database for
each suite run, and cover up/down/up, duplicate device IDs, foreign keys, enabled
states, and repeatable seeding. See the [backend guide](../backend/README.md#development-checks).

The [local platform workflow](../.github/workflows/local-platform.yml) runs these
checks in a separate job alongside backend lint/tests and frontend
formatting/type checks, component tests, and a production build on every push
and pull request. All jobs report failures independently. See the
[CI guide](../docs/ci.md) for triggers, cache behavior, and local reproduction.
For Python linting, use the backend's locked development dependencies and:

```sh
python -m ruff check --config backend/pyproject.toml backend simulator tests
python -m ruff format --check --config backend/pyproject.toml backend simulator tests
```

Use repeatable simulator scenarios where possible and keep fixture data free of
secrets. Follow the shared [conventions](../CONTRIBUTING.md).
