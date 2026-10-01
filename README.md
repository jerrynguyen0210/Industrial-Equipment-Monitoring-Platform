# Industrial Equipment Monitoring Platform

A lab platform that moves equipment temperature data from an ESP32 or simulator
through MQTT and a durable gateway to PostgreSQL and a React dashboard.

## What runs

| Component | Purpose |
| --- | --- |
| [Firmware](firmware/README.md) | Reads a DS18B20 probe, publishes telemetry, and reports presence. |
| [Gateway](gateway/README.md) | Validates MQTT messages, queues them in SQLite, and forwards HTTP batches. |
| [Backend](backend/README.md) | Registers devices, ingests telemetry, stores history, and evaluates prototype alerts. |
| [Frontend](frontend/README.md) | Shows devices, online status, recent readings, history, and service health. |
| [Simulator](simulator/README.md) | Generates repeatable test readings over MQTT or HTTP. |
| [Infrastructure](infra/README.md) | Runs PostgreSQL, Mosquitto, the backend, and the frontend with Compose. |

Data follows this path:

```text
ESP32 or simulator -> Mosquitto -> native gateway -> backend -> PostgreSQL
Browser -> frontend -> backend API -> PostgreSQL
```

This is a controlled lab prototype. MQTT and device heartbeats use plaintext on
the local network, the dashboard has no operator login, and production backup,
fleet provisioning, and alert operations are incomplete.

## Start the lab system

1. On a 64-bit Raspberry Pi OS, Debian, or Ubuntu host, open a terminal at the
   repository root.
2. Run:

   ```sh
   ./agents/server_scripts/run-stack.sh
   ```

3. Enter the server and ESP32 LAN addresses when prompted.
4. Open the dashboard address printed by the script, usually
   `http://<server-address>:8080`.
5. Check or stop the stack with:

   ```sh
   ./agents/server_scripts/run-stack.sh status
   ./agents/server_scripts/run-stack.sh logs
   ./agents/server_scripts/run-stack.sh stop
   ```

The launcher provisions credentials, starts the four Compose services, applies
migrations, seeds the demo registry, and checks health. It preserves existing
configuration and data when rerun.

Continue with the [step-by-step setup guide](Setup_Guide/README.md) to connect the
gateway and ESP32. Configuration ownership is summarized in
[docs/configuration.md](docs/configuration.md).

## Verify changes

```sh
docker compose config --quiet
python3 tests/compose_smoke.py
```

The smoke test creates and removes an isolated Compose project. Component test
commands are in each component README, and CI details are in [docs/ci.md](docs/ci.md).

## Contribute

Follow [CONTRIBUTING.md](CONTRIBUTING.md) and the coding guide in the component
you change. Shared contracts and architecture notes live in [docs/](docs/README.md).

## License

A project license has not been selected. Add a `LICENSE` file before distribution.
