# Firmware

Device-side sensor sampling, equipment telemetry, and connectivity.

## Development guide

Read [Firmware Coding Conventions](CODING_CONVENTIONS.md) for code structure,
sampling, timing, telemetry identity, connectivity, security, and hardware validation.

## Planned contents

- Firmware source and supported board definitions.
- Sensor drivers and device configuration examples.
- Workstream unit tests and hardware validation instructions.

## Setup and validation

TODO: Select supported hardware and toolchains, then document build, flash, and
test commands. No firmware implementation exists yet.

The architecture baseline is ESP32 with ESP-IDF. Build, flash, serial debugging,
and sensor access remain native; the firmware is not a Compose service and
requires no Docker device passthrough. Compose can supply a development MQTT
broker independently with `docker compose up -d mosquitto` from the repository root.

The broker publishes only on the computer's loopback interface by default.
For a physical ESP32, follow the [LAN broker setup](../infra/README.md#gateway-and-firmware-outside-compose)
and configure the device with the computer's LAN address, not `localhost` or the
Compose-only `mosquitto` hostname. Board-specific build/flash commands remain for
the firmware implementation workstream.

Document the device-to-gateway contract in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
