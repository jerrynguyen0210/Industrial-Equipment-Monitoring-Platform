# Firmware coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md), ESP-IDF 5.5.4 APIs, and these rules.

## Code and tasks

- Use C with clear module ownership and small public headers.
- Check every ESP-IDF and driver result; log stable state/reason fields.
- Bound task stacks, queues, retries, timeouts, and allocations.
- Avoid blocking callbacks. Define ownership before sharing data across tasks.
- Never erase NVS automatically to recover from a configuration error.

## Sensor and telemetry

- Publish only finite readings inside the selected sensor's valid range.
- Keep disconnected, CRC, conversion, and invalid-value failures distinct.
- Invalid samples must not carry a numeric value or become telemetry.
- Preserve boot ID and per-boot sequence identity across retries.
- Use null `measured_at` until wall-clock time is trustworthy.
- Publish telemetry at QoS 1 with retain disabled; retry identical bytes.
- Treat broker acknowledgement as broker receipt only.

## Configuration and security

- Validate Device ID, network, credential, GPIO, interval, and source before use.
- Never log passwords, entry keys, or full telemetry payloads.
- Treat `sdkconfig`, build output, and firmware images as secret-bearing files.
- Keep synthetic and manual input modes explicit in configuration and logs.
- Use TLS before any deployment outside a trusted lab network.

## Validation checklist

- [ ] Host tests cover identity, sequence bounds, encoding, and input validation.
- [ ] Firmware builds with the pinned ESP-IDF version.
- [ ] Hardware tests cover probe disconnect/reconnect and a trusted reference.
- [ ] Wi-Fi reconnect preserves identity; reboot changes boot ID and resets sequence.
- [ ] Queue-full, broker outage, and restart behavior are recorded.
