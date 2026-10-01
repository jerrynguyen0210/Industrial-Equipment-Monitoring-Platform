# Documentation

Start with the [setup guide](../Setup_Guide/README.md) for installation, hardware,
operations, and release planning.

## Contracts and design

| Document | Purpose |
| --- | --- |
| [Local platform](local-platform.md) | Compose architecture and development boundaries. |
| [Configuration](configuration.md) | Environment files, precedence, defaults, and secrets. |
| [Health API](health-api.md) | Liveness and database readiness responses. |
| [Device API](device-status-api.md) | Registration, deletion, presence, and latest reading. |
| [History API](history-api.md) | Time ranges, ordering, limits, and chart gaps. |
| [Registry](registry.md) | Site, gateway, and device ownership. |
| [MQTT contract](mqtt-topic-contract.md) | Topics, credentials, QoS, and duplicate rules. |
| [Telemetry API](telemetry-api-contract.md) | Batch validation, authorization, and outcomes. |
| [Telemetry storage](telemetry-storage.md) | PostgreSQL fields, identity, time, and recovery. |
| [Temperature alerts](temperature-alert-flow.md) | Prototype alert state and thresholds. |

## Testing and operations

| Document | Purpose |
| --- | --- |
| [CI](ci.md) | Automated checks and local reproduction. |
| [Windows Docker testing](docker-testing.md) | PowerShell procedure for the local stack. |
| [Simulator](../simulator/README.md) | Repeatable MQTT and HTTP test data. |
| [Shared tests](../tests/README.md) | Contract fixtures and Compose smoke tests. |

The PDFs in this directory record requirements and architecture decisions. When
they conflict with an implemented contract above, use the newer implemented
contract and record unresolved decisions in an issue.

## Writing rules

- Use relative links and descriptive filenames.
- Put commands in numbered procedures with the expected result.
- Keep one authoritative procedure and link to it instead of copying it.
- Explain failure boundaries where a command can lose data or expose a secret.
- Reference the related `IEMP-<issue-number>` for planned work or decisions.

Contribution rules are in [CONTRIBUTING.md](../CONTRIBUTING.md).
