# Local platform bootstrap

## Scope and architecture

The root Compose stack provides reproducible local startup of PostgreSQL,
Mosquitto, FastAPI, and React/TypeScript. These runtimes follow the proposed
implementation baseline in the [requirements specification](Industrial_Equipment_Monitoring_Requirements.pdf)
and the component boundaries in the [architecture decision package](Technical_Lead_Architecture_Decision_Package_Sprint01.pdf).

The backend currently exposes health endpoints and the frontend displays their
result. This makes container startup and browser-to-API-to-database connectivity
reviewable before application features arrive. It does not implement the approved
telemetry ingestion contract, migrations, registry, authentication, or alerts.
No demo readings or successful ingestion responses are fabricated.

The backend depends on PostgreSQL only. It does not consume device MQTT; the
native C++ gateway will own MQTT intake, SQLite buffering, and batch forwarding.
Mosquitto has no application dependency and remains running during a backend
outage. Firmware and gateway lifecycles, hardware access, and queue files stay
outside Compose. A full-stack shutdown intentionally stops the development broker.

## Local choices

- Use digest-pinned multi-platform images, hash-locked Python dependencies, and
  `npm ci` with a committed lockfile. No host build artifacts are required.
- Keep PostgreSQL on an internal network with no host port. A separate bridge
  serves the published application/MQTT ports, bound to loopback by default.
- Use project-scoped named volumes for PostgreSQL and Mosquitto. Application
  images are disposable; broker persistence does not replace the gateway queue.
- Gate initial startup on health checks. Readiness checks real SQL authentication
  and query execution; API liveness and frontend availability remain independent
  of dependency outages.
- Serve React through unprivileged Nginx and proxy `/api/` on the same origin.
  Container DNS is resolved inside Nginx and refreshed after backend replacement.
- Permit local-only development credentials, HTTP, and anonymous MQTT so a clean
  checkout starts with one command. These are explicitly scoped development
  exceptions, not a change to deployed TLS or authentication requirements.
- Use a single local database owner during the health-only bootstrap. Application
  migrations and a least-privilege runtime role belong with persistence work.

## Evidence and boundaries

[The smoke test](../tests/compose_smoke.py) exercises real containers, SQL, MQTT,
outages, proxy recovery, and volume reuse in an isolated project. It is configured
in CI. Passing mocked unit tests or Compose validation alone does not establish
container startup, hardware integration, backup recovery, or gateway durability.

Operational commands and configuration live in [infra/README.md](../infra/README.md).
The broader MVP security, ingestion, firmware, and reliability milestones remain
open; this document records only local platform implementation choices.
