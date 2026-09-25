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

The [CI workflow](../.github/workflows/local-platform.yml) has an optional native
build hook. It reports the build as skipped until `gateway/CMakeLists.txt` exists.
Once that file is committed, every push and pull request runs:

```sh
cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=17 -DCMAKE_CXX_STANDARD_REQUIRED=ON
cmake --build gateway/build --parallel 2
```

These commands run from the repository root with the Ubuntu 24.04 runner's CMake
and C++ compiler. Add any required system dependencies and gateway test commands
to the workflow with the first implementation. Configuration or compilation
errors fail the job; the missing-project skip is not gateway validation evidence.

The architecture baseline is native C++17 with a local SQLite queue. The gateway
is deliberately outside Compose so hardware access and queue storage stay under
the gateway host's control. First run `python infra/mosquitto/provision.py` from
the repository root. Then start the development broker with `docker compose up
-d mosquitto`, or start the entire local platform with `docker compose up`.
A gateway on the same computer uses MQTT `127.0.0.1:1883` and backend base URL
`http://127.0.0.1:8000`. The backend ingestion endpoint is implemented; the
native gateway MQTT client and forwarding loop are not.

[.env.example](.env.example) records planned `MQTT_HOST`, `MQTT_PORT`,
`MQTT_USERNAME`, `MQTT_PASSWORD_FILE`, `API_BASE_URL` (including `/api`), and
`GATEWAY_API_KEY` settings. Copy it to an
ignored `.env` for local values. No gateway runtime loads this file yet, and the
API credential placeholder does not enable HTTP authentication. Provision a unique
API bearer token separately from the generated MQTT password; keep both out of
frontend configuration. See the [configuration guide](../docs/configuration.md)
and [MQTT topic contract](../docs/mqtt-topic-contract.md).

See [hardware connectivity and independent service lifecycles](../infra/README.md#gateway-and-firmware-outside-compose)
for Pi/LAN settings and backend-outage testing. Keep the SQLite queue outside
Compose volumes. A backend outage must not stop native MQTT acquisition.

Document inbound and outbound contracts in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
