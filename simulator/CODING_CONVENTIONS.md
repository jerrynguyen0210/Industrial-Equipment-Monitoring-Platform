# Simulator coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these simulator rules.

## Determinism

- Derive all generated data from explicit scenario inputs and a private seeded
  random generator.
- Never consult wall time during event generation; accept an explicit start time.
- Keep event bytes stable for the same version, runtime, seed, and options.
- Record scenario inputs and source revision in summaries, without credentials.

## Identity and transport

- Preserve `(device_id, boot_id, sequence_number)` and immutable content on retry.
- Reset sequence and uptime only at an explicit simulated reboot.
- Keep MQTT device messages separate from HTTP gateway batches.
- Use QoS 1 and no retain for MQTT; distinguish broker acknowledgement from
  backend confirmation.
- Do not hide rejected or unconfirmed events with automatic retries.
- Bound event count, batch size, pacing, timeout, and output.

## Scenarios and reporting

- Keep normal, fault, replay, and load scenarios explicit and composable.
- Report attempted, confirmed, rejected, unconfirmed, and unsent counts.
- Exit nonzero for transport, response, or expectation failure.
- Use injected clocks, sleeps, and transports in unit tests.
- Never include passwords, bearer tokens, or full secret-bearing environment.

## Validation checklist

- [ ] Unit tests prove repeatability, profiles, reboot identity, and batch limits.
- [ ] CLI tests cover invalid arguments, cancellation, and response failure.
- [ ] MQTT and HTTP modes preserve the same event contract.
- [ ] Shared fixtures remain versioned and free of secrets.
