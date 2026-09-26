# Documentation

Shared architecture, interface contracts, project decisions, and operating guides.

## Project reference documents

- [Requirements specification](Industrial_Equipment_Monitoring_Requirements.pdf):
  draft baseline for functional, security, reliability, and acceptance requirements.
- [Sprint 01 architecture decision package](Technical_Lead_Architecture_Decision_Package_Sprint01.pdf):
  draft architecture review with component boundaries, proposed ADRs, and open
  implementation decisions.
- [Sprint 01 telemetry and ingestion contract approval](Technical_Lead_Telemetry_Ingestion_Contract_Approval_Sprint01.pdf):
  approved implementation contract, including event identity, timestamp ownership,
  batch limits, per-item outcomes, and fixtures. Backend and gateway review
  acknowledgements remain pending in this report.

Use the approved ingestion contract for decisions it resolves in the older source
documents. Track unresolved behavior explicitly; the coding guides do not close
review gates or establish implementation and test completion.

## Planned documentation

The [local platform bootstrap](local-platform.md) records the implemented Compose
scope and development exceptions. Executable setup, hardware connectivity, and
operational commands are in the [infrastructure runbook](../infra/README.md).
The [configuration guide](configuration.md) lists service environment templates,
local defaults, loading precedence, and secret handling.
The [health API contract](health-api.md) defines backend liveness, database
readiness, response schemas, and dependency failure behavior for local integration.
The [device status API](device-status-api.md) defines the current device and latest
reading response, timestamp interpretation, and unavailable-data behavior.
The [temperature history API](history-api.md) defines bounded measurement-time
queries, ordering, truncation, and chart segment breaks.
The [minimum registry](registry.md) documents site/gateway/device ownership,
enabled states, PostgreSQL constraints, migrations, demo seeding, and verification.
The [telemetry storage schema](telemetry-storage.md) documents v1 fields, event
identity uniqueness, UTC timestamps, device/time indexes, and migration recovery.
The [telemetry API validation contract](telemetry-api-contract.md) defines request,
quality, and response models, per-item validation, stable errors, and generated
[OpenAPI examples](telemetry-openapi.json) for the implemented ingestion endpoint.
The [local MQTT topic contract](mqtt-topic-contract.md) defines authenticated
device-to-gateway topics, QoS 1 delivery, duplicate handling, and retained policy.
The [simulator quick start](../simulator/README.md) exercises credentials, durable
persistence, matching retries and mixed per-item rejections over HTTP.
The [Windows Docker testing guide](docker-testing.md) gives PowerShell commands
for automated smoke tests, registry acceptance, and manual database inspection.
The [CI guide](ci.md) documents automatic verification on every push and pull
request, dependency caches, the optional gateway build, and local reproduction.

- System architecture and workstream boundaries.
- Device telemetry schemas, gateway protocols, and backend API contracts.
- Architecture decision records explaining significant technology choices.
- Local development, deployment, troubleshooting, and operations guides.

## Documentation conventions

Use descriptive Markdown filenames and relative links. Reference the relevant
`IEMP-<issue-number>` when recording implementation decisions or planned work.
Keep workstream-specific setup commands in that workstream's README and link
them from shared guides.

TODO: Maintain version-controlled architecture and contract specifications as
implementation decisions are made, with traceability to the reference documents.

Branch, commit, and task ID rules live in [CONTRIBUTING.md](../CONTRIBUTING.md).
