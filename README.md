# Industrial Equipment Monitoring Platform

A platform for collecting equipment telemetry, processing it through an edge
gateway and backend, and presenting equipment status in a monitoring interface.

## Project status

Repository scaffolding is in place. Application code, runtime choices, deployment
targets, and executable setup commands are still to be defined.

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

Devices (or the simulator) send telemetry through the gateway to the backend.
The frontend reads equipment status through backend APIs. Protocols, schemas,
and deployment boundaries will be documented in `docs/` before integration.

## Getting started

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) for issue IDs, branches, and commits.
2. Select a workstream and read its directory README.
3. Create or select a GitHub issue before implementation.
4. Add prerequisites and verified setup commands to the workstream README when
   its runtime is introduced.

### Prerequisites

TODO: Document supported toolchains and versions for each workstream.

### Local development

TODO: Document environment configuration and commands for starting the platform.
Commit sanitized `.env.example` files when configuration is introduced.

### Testing

TODO: Add verified commands for unit, integration, and end-to-end tests. No test
runner or automated checks are configured yet.

### Deployment

TODO: Document deployment targets, provisioning, and rollback in `infra/` and
`docs/`.

## Contributing

Use issue IDs such as `IEMP-42`, branches such as
`codex/feat/iemp-42-telemetry-ingestion`, and Conventional Commits such as
`feat(backend): add telemetry ingestion [IEMP-42]`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete conventions.

## License

TODO: Choose a license and add a `LICENSE` file before distributing the project.
