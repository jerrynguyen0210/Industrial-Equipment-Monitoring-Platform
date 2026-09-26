# Industrial Equipment Monitoring Platform

A platform for collecting equipment telemetry, processing it through an edge
gateway and backend, and presenting equipment status in a monitoring interface.

## Project status

The local platform runs PostgreSQL, Mosquitto, a FastAPI health and telemetry API,
and a React/TypeScript dashboard shell with Docker Compose. The dashboard has
Overview (`/`) and Service Status (`/status`) routes and displays backend and
database readiness. The [API-mode simulator](simulator/README.md) exercises
authenticated batch ingestion, per-item outcomes, persistence and retries, with
deterministic temperature profiles, seeded noise, sampling intervals and simulated
reboots. Equipment-specific views, the native gateway, and firmware remain
separate implementation workstreams.

## Repository structure

| Directory | Responsibility |
| --- | --- |
| [firmware/](firmware/README.md) | Device firmware, sensor sampling, and device telemetry. |
| [gateway/](gateway/README.md) | Edge connectivity, protocol translation, and telemetry forwarding. |
| [backend/](backend/README.md) | Ingestion, storage, APIs, and monitoring rules. |
| [frontend/](frontend/README.md) | Equipment dashboards and user-facing workflows. |
| [simulator/](simulator/README.md) | Repeatable virtual devices and telemetry scenarios. |
| [infra/](infra/README.md) | Local environment and deployment configuration. |
| [docs/](docs/README.md) | Architecture, interface contracts, decisions, and runbooks. |
| [tests/](tests/README.md) | Cross-workstream integration and end-to-end tests. |

Unit tests belong alongside the workstream they exercise. Shared fixtures and
tests spanning multiple workstreams belong in `tests/`.

## Planned data flow

Devices (or the simulator) publish to local Mosquitto. The native gateway will
buffer readings in SQLite and forward HTTP batches to the backend. The frontend
uses backend APIs; the backend owns PostgreSQL access. Stopping the backend does
not stop Mosquitto. See the [architecture references](docs/README.md).

## Getting started

From the repository root:

```powershell
python infra/mosquitto/provision.py
docker compose up -d --build --wait
```

Open **http://localhost:8080** for Overview or
**http://localhost:8080/status** for Service Status. The status view reports
whether the backend can query PostgreSQL through `/api/health/ready`.
The provisioner creates ignored, local MQTT credentials and refuses to replace
an existing credential directory. Run it only once for a persistent stack;
later starts need only the Compose command. First startup downloads images and
builds both applications. No `.env` file is required, and the readiness check
does not require a database migration. Run migrations explicitly before using
registry or telemetry persistence; see the [Docker test guide](docs/docker-testing.md).

### Prerequisites

Docker Engine with Docker Compose v2.24+ (including newer versions), or Docker
Desktop running Linux containers. The Docker daemon must be running. Allow about
2 GB of memory for these services, plus image-build overhead, and free host ports
8080, 8000, and 1883. Host Python is needed for the one-time MQTT credential
provisioner; the isolated smoke test requires Python 3.13+. Node.js is needed
only for native frontend development.

### Local development

Defaults bind published ports to loopback and are for local development with
synthetic data. Optional overrides are listed in [.env.example](.env.example);
copy it to `.env` only when changing defaults.

Service examples are available for [backend](backend/.env.example),
[frontend](frontend/.env.example), [gateway](gateway/.env.example), and
[simulator](simulator/.env.example). The [configuration guide](docs/configuration.md)
explains which files are loaded, local addresses, and credential placeholders.

| Service | Host address |
| --- | --- |
| Frontend | http://localhost:8080 |
| Backend liveness | http://localhost:8000/health |
| Backend database readiness | http://localhost:8000/ready |
| MQTT | `127.0.0.1:1883` |
| PostgreSQL | Internal only; use `docker compose exec postgres ...`. |

```powershell
docker compose up -d --wait  # Start in the background and wait for health checks.
docker compose ps
docker compose logs -f
docker compose up -d --build --wait  # Rebuild after application changes.
docker compose down         # Remove containers; retain named data volumes.
```

Gateway and firmware are intentionally outside Compose so native builds, serial
debugging, flashing, and the gateway's local SQLite queue remain independent.
See [infra/README.md](infra/README.md) for hardware connectivity, configuration,
storage, independent service lifecycles, and troubleshooting.

### Testing

```powershell
docker compose config --quiet
python tests/compose_smoke.py
```

The smoke test requires Python 3.13+ and Docker. It creates a separate temporary
Compose project, provisions its own MQTT credentials, exercises startup, API
routing, MQTT, outages, and persistence,
then removes only its own test resources. See [tests/README.md](tests/README.md)
and the workstream READMEs for unit, formatting, and build checks. The
[local platform workflow](.github/workflows/local-platform.yml) runs these checks
on every push and pull request, alongside backend lint/tests and frontend
formatting/type checks, component tests, and a production build. A native gateway
build activates when its CMake project exists. See the [CI guide](docs/ci.md)
for dependency caching, failure handling, and local reproduction.

### Deployment

This Compose stack is a local development environment. Deployed TLS, application
authentication, device credentials, database migrations, and backup/restore
automation remain future work. See the [local platform decision record](docs/local-platform.md).

## Contributing

Use issue IDs such as `IEMP-42`, branches such as
`codex/feat/iemp-42-telemetry-ingestion`, and Conventional Commits such as
`feat(backend): add telemetry ingestion [IEMP-42]`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete conventions.

Read the conventions guide for the workstream you are changing:

| Workstream | Guide |
| --- | --- |
| Firmware | [Firmware Coding Conventions](firmware/CODING_CONVENTIONS.md) |
| Gateway | [Gateway Coding Conventions](gateway/CODING_CONVENTIONS.md) |
| Backend | [Backend Coding Conventions](backend/CODING_CONVENTIONS.md) |
| Frontend | [Frontend Coding Conventions](frontend/CODING_CONVENTIONS.md) |
| Simulator | [Simulator Coding Conventions](simulator/CODING_CONVENTIONS.md) |
| Infrastructure | [Infrastructure Coding Conventions](infra/CODING_CONVENTIONS.md) |
| Shared tests | [Shared Testing Coding Conventions](tests/CODING_CONVENTIONS.md) |

## License

TODO: Choose a license and add a `LICENSE` file before distributing the project.
