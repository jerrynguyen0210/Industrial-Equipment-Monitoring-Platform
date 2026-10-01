# Industrial Equipment Monitoring Platform

A platform for collecting equipment telemetry, processing it through an edge
gateway and backend, and presenting equipment status in a monitoring interface.

## Project status

The local platform runs PostgreSQL, Mosquitto, a FastAPI health and telemetry API,
and a React/TypeScript dashboard with Docker Compose. The dashboard shows stored
device readings, history, and service readiness. The native C++17 gateway
validates MQTT readings, queues them in SQLite, and forwards HTTP batches to the
backend. ESP32 firmware samples one DS18B20 probe and publishes valid readings;
the probe still needs to be wired on each device. The
[simulator](simulator/README.md) supplies repeatable virtual readings for tests.
This remains a lab prototype; see the [setup and customer deployment guide](Setup_Guide/README.md).

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
| [agents/server_scripts/](agents/server_scripts/README.md) | Local stack launcher. |
| [agents/hardware_script/](agents/hardware_script/README.md) | ESP32 firmware build and flash helper. |

Unit tests belong alongside the workstream they exercise. Shared fixtures and
tests spanning multiple workstreams belong in `tests/`.

## Data flow

The simulator or ESP32 publishes to local Mosquitto. The native gateway validates
and queues MQTT readings in SQLite, then forwards HTTP batches to the backend.
The frontend uses backend APIs, and the backend owns PostgreSQL access. Stopping
the backend does not stop Mosquitto. See the
[architecture references](docs/README.md).

## Getting started

1. Open a terminal in this repository folder on Linux.

2. Start the complete stack on the current machine:

   ```sh
   ./agents/server_scripts/run-stack.sh
   ```

   Choose LAN access when prompted. For example, use `192.168.0.50` for the
   server and `192.168.0.114` for the ESP32.

3. Open the dashboard address printed by the script, such as
   `http://192.168.0.50:8080`.

4. Check status or logs:

   ```sh
   ./agents/server_scripts/run-stack.sh status
   ./agents/server_scripts/run-stack.sh logs
   ```

5. Stop the stack while preserving data:

   ```sh
   ./agents/server_scripts/run-stack.sh stop
   ```

6. Continue with the [setup guide](Setup_Guide/README.md) for hardware or
   deployment.

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
formatting/type checks, component tests, and a production build. The native
gateway build and MQTT intake tests run in CI. See the [CI guide](docs/ci.md)
for dependency caching, failure handling, and local reproduction.

### Deployment

This Compose stack is a local development environment. Database migrations are
implemented but run explicitly; deployed MQTT TLS, dashboard authentication,
fleet provisioning, and backup/restore automation remain release gates. See the
[customer deployment guide](Setup_Guide/04-customer-deployment.md).

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
