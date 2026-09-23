# Shared Tests

Tests and fixtures that validate integration across workstreams.

## Development guide

Read [Shared Testing Coding Conventions](CODING_CONVENTIONS.md) for suite placement,
fixtures, contract verification, reliability scenarios, and acceptance evidence.

## Planned contents

- Contract tests for telemetry and API boundaries.
- Integration tests for device/simulator, gateway, and backend interactions.
- End-to-end monitoring workflows and shared fixtures.

Workstream unit tests belong with the implementation they exercise. Add shared
test subdirectories here as suites are introduced.

## Setup and validation

The local-platform smoke suite uses Python 3.13+ standard-library tools and Docker
Compose v2.24+. From the repository root with Docker running:

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
- Mosquitto and frontend remain available while the backend is stopped.
- Database failure returns readiness HTTP 503 with structured JSON through both
  the backend and frontend proxy while `/health` remains 200, and readiness
  recovers after PostgreSQL returns.
- The frontend proxy recovers after backend container recreation.
- SQL data and retained MQTT messages survive `down` followed by `up`.

Cleanup removes only the generated project's containers, networks, and test
volumes, including on ordinary failures. Abruptly killing Python can leave a test
project behind; inspect `docker compose ls --all` and use its exact generated
project name when cleaning it up. No hardware or native gateway is exercised.
This is infrastructure evidence, not ingestion, queue durability, or MVP acceptance.

The [local platform workflow](../.github/workflows/local-platform.yml) runs these
checks in a separate job alongside backend lint/tests and frontend
formatting/type checks, component tests, and a production build on every push
and pull request. All jobs report failures independently. See the
[CI guide](../docs/ci.md) for triggers, cache behavior, and local reproduction.
For Python linting, use the backend's locked development dependencies and:

```sh
python -m ruff check --config backend/pyproject.toml backend tests/compose_smoke.py
python -m ruff format --check --config backend/pyproject.toml backend tests/compose_smoke.py
```

Use repeatable simulator scenarios where possible and keep fixture data free of
secrets. Follow the shared [conventions](../CONTRIBUTING.md).
