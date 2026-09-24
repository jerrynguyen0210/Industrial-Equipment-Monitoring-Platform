# Simulator

Virtual devices and repeatable telemetry scenarios for development and testing.

## Development guide

Read [Simulator Coding Conventions](CODING_CONVENTIONS.md) for reproducible
scenarios, event identity, fault injection, bounded workloads, and run reporting.

## Planned contents

- Device models and configurable telemetry generation.
- Normal operation, fault, and connectivity scenarios.
- Reproducible scenario inputs and workstream unit tests.

## Setup and validation

TODO: Select the runtime, then document configuration, scenario execution, and
test commands. No simulator implementation exists yet.

[.env.example](.env.example) records planned local MQTT host/port settings plus
an API base URL and test gateway credential placeholder for a future API-only
mode. Copy it to an ignored `.env` for local values. No runtime loads these
settings yet. Device mode uses MQTT; API-only mode will bypass the real gateway
and require its own provisioned test credential. See the
[configuration guide](../docs/configuration.md).

Use the same device telemetry contract as firmware, documented in
[docs/](../docs/README.md). Follow the shared [conventions](../CONTRIBUTING.md).
