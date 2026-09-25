# Local platform bootstrap

## Scope and architecture

The root Compose stack provides reproducible local startup of PostgreSQL,
Mosquitto, FastAPI, and React/TypeScript. These runtimes follow the proposed
implementation baseline in the [requirements specification](Industrial_Equipment_Monitoring_Requirements.pdf)
and the component boundaries in the [architecture decision package](Technical_Lead_Architecture_Decision_Package_Sprint01.pdf).

The backend exposes health and authenticated telemetry ingestion endpoints, and
the frontend displays health. This makes container startup and browser-to-API-to-
database connectivity reviewable. The backend also includes a
[minimum persisted registry](registry.md), explicit Alembic migrations, and a demo
seed command. The native gateway and alerts are still unimplemented. No demo
readings are inserted during ordinary stack startup.

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
- Generate ignored local MQTT credentials before the first Compose start. The
  broker requires passwords and topic ACLs; plain HTTP and unencrypted MQTT are
  scoped development exceptions, not a change to deployed TLS requirements.
- Use a single local database owner for development. Registry migrations are
  explicit deployment commands; separate migration/runtime roles for deployed
  environments remain an infrastructure provisioning task.

## Evidence and boundaries

[The smoke test](../tests/compose_smoke.py) exercises real containers, SQL, MQTT,
outages, proxy recovery, and volume reuse in an isolated project. It is configured
in CI. Passing mocked unit tests or Compose validation alone does not establish
container startup, hardware integration, backup recovery, or gateway durability.

Operational commands and configuration live in [infra/README.md](../infra/README.md).
The broader MVP security, ingestion, firmware, and reliability milestones remain
open; this document records only local platform implementation choices.
