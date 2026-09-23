# Gateway

Edge connectivity, protocol translation, and telemetry forwarding to the backend.

## Development guide

Read [Gateway Coding Conventions](CODING_CONVENTIONS.md) for protocol boundaries,
durable queue handling, batching, retries, security, and recovery validation.

## Planned contents

- Device protocol adapters and telemetry normalization.
- Connection recovery, buffering, and forwarding logic.
- Configuration examples and workstream unit tests.

## Setup and validation

TODO: Implement the native gateway and document installation, configuration, run,
and test commands. No gateway implementation exists yet.

The architecture baseline is native C++17 with a local SQLite queue. The gateway
is deliberately outside Compose so hardware access and queue storage stay under
the gateway host's control. Start the development broker using `docker compose up
-d mosquitto` from the repository root, or start the entire local platform with
`docker compose up`. A gateway on the same computer uses MQTT `127.0.0.1:1883` and
backend base URL `http://127.0.0.1:8000`. Only backend health endpoints exist so far.

See [hardware connectivity and independent service lifecycles](../infra/README.md#gateway-and-firmware-outside-compose)
for Pi/LAN settings and backend-outage testing. Keep the SQLite queue outside
Compose volumes. A backend outage must not stop native MQTT acquisition.

Document inbound and outbound contracts in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
