# Firmware Coding Conventions

Development rules for sensor acquisition, device identity, telemetry, and device
connectivity. These are implementation expectations; no firmware implementation
or automated checks are currently present.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep supported boards, toolchain versions, build, flash, and test commands in
  [README.md](README.md). Document pin assignments and wiring with each board.
- Follow the [project reference documents](../docs/README.md#project-reference-documents)
  for requirements and the approved telemetry contract. Draft architecture
  proposals are not finalized by this guide.
- Record changes to hardware assumptions or shared contracts in `docs/` and link
  the implementation issue. Do not invent wire fields to resolve an open decision.

## 2. Code style and structure

- Use the selected language's naming conventions consistently and configure its
  formatter and compiler checks. Use domain names such as sensor, sample, and boot.
- Separate board configuration, sensor drivers, sampling, payload encoding, and
  network transport. Keep protocol details out of sensor-conversion logic.
- Keep functions focused and make ownership, return values, and errors explicit.
  Check driver and SDK return codes; propagate failures with useful context.
- For C/C++, use explicit-width integers for protocol fields, checked conversions,
  bounded buffers, and clear resource ownership. Document byte order and alignment
  when encoding binary data; do not transmit raw in-memory structures.
- Put pin numbers, timeouts, sampling intervals, and conversion factors in named
  configuration or constants with units. Avoid mutable global state where possible.
- Explain hardware constraints in comments. Remove unused code and link TODOs to
  issues rather than leaving silent stubs in the sampling path.

## 3. Scheduling, memory, and concurrency

- Keep sampling independent of network reconnects. Bound all driver and network
  waits so one failed peripheral cannot indefinitely block the device.
- Use a monotonic clock for intervals and uptime. Handle timer wraparound and
  distinguish elapsed time from UTC wall-clock time.
- Keep interrupt handlers short. Defer blocking I/O, allocation, and expensive
  processing to task context; use SDK-supported synchronization primitives.
- Document ownership of buffers shared across tasks or callbacks. Do not reuse a
  transmit buffer until its consumer is finished with it.
- Set and measure stack, heap, queue, and payload limits on the supported board.
  Avoid uncontrolled allocation in frequent sampling or interrupt paths.
- Define watchdog behavior around actual progress. Repeatedly feeding a watchdog
  must not hide a stalled acquisition task or an endless retry loop.

## 4. Sensor readings and quality

- Document the sensor model, supported range, calibration, units, and conversion
  precision. Test conversion boundaries and sensor-disconnect behavior.
- The MVP telemetry metric is `temperature` and its unit is `celsius`. Emit only
  finite readings within the selected sensor's documented range as valid telemetry.
- Distinguish zero from missing or failed measurements. Never substitute zero, a
  random value, or a previous sample and present it as a new valid measurement.
- The approved v1 reading contract accepts `quality.reading = valid`. The full
  disconnected-sensor and invalid-reading payload is still an open contract item;
  implement its required explicit status through the agreed status contract when
  defined, without fabricating a valid telemetry reading in the meantime.
- Apply calibration or filtering only through documented rules. Record which value
  is transmitted and test whether processing changes threshold behavior.

## 5. Event identity and time

- Identify a reading by `(device_id, boot_id, sequence_number)`. Generate a new
  `boot_id` on each boot and increase the sequence number within that boot.
- Assign identity when creating the event. Retries preserve that identity and all
  immutable telemetry content; a reconnect does not create a new boot or sample.
- Define sequence-number capacity and exhaustion behavior. Do not wrap or reuse an
  event identity within a boot.
- Own `measured_at` and `device_uptime_ms`. Use UTC measurement time when trusted,
  otherwise null when no trustworthy measurement time is available.
- Use the approved clock-quality vocabulary: `synchronised`, `unsynchronised`,
  `estimated`, or `unknown`. Do not mark an unsynchronized device as synchronized.
- Do not assign `gateway_received_at` or `backend_received_at`; those timestamps
  belong to the gateway and backend respectively.
- Preserve an event's original timestamp and quality during retransmission, even
  if the device clock becomes synchronized after the measurement.

## 6. Connectivity and delivery

- Implement the documented device-to-gateway topic and payload contract. Keep
  device payloads distinct from the gateway's HTTPS batch envelope.
- Use the agreed MQTT QoS 1 semantics and expect duplicate delivery. A broker
  acknowledgement does not prove durable gateway storage or backend acceptance.
- Bound reconnect attempts with backoff and jitter. Continue acquisition according
  to a documented local buffering or loss policy while the connection is down.
- Make local buffer capacity, overflow behavior, and any pre-gateway losses
  observable. The platform recovery guarantee starts at gateway storage commit.
- Define heartbeat behavior separately from historical telemetry replay. Do not
  republish old samples as evidence of current device activity.
- Test connection loss and recovery without requiring a manual device reset.

## 7. Configuration, security, and device lifecycle

- Keep Wi-Fi credentials, private keys, and device credentials out of source,
  logs, fixtures, and committed firmware configuration examples.
- Use authenticated TLS for deployed MQTT connections and verify broker identity.
  Document certificate provisioning, renewal, and clock requirements.
- Restrict each device to its own allowed topics. Do not share a privileged broker
  account across all devices.
- Validate configuration before applying it. Document persistence behavior and
  avoid excessive flash writes for frequently changing counters or state.
- Define safe behavior for reboot, brownout, invalid configuration, and peripheral
  failure. A monitoring failure must remain distinguishable from a healthy reading.
- If remote updates are introduced, authenticate firmware artifacts and document
  interrupted-update recovery and version compatibility before enabling them.

## 8. Diagnostics and validation

- Log firmware version, reset reason, connection transitions, and sensor failures
  with bounded output. Avoid logging every sample at normal operating verbosity.
- Expose useful counters such as sampling failures, dropped samples, reconnects,
  queue usage, and uptime without exposing credentials.
- Unit-test conversion, encoding, identity, and clock logic within `firmware/`.
  Keep shared gateway/backend contract and end-to-end tests in
  [tests/](../tests/README.md).
- Use hardware validation for pin behavior, sensor disconnects, power cycles,
  memory limits, and sustained sampling. Host mocks do not prove board behavior.
- Record board revision, sensor, wiring, firmware commit, toolchain, commands,
  workload, and results so another developer can reproduce hardware checks.
- Add verified build and validation commands with the first implementation. State
  which hardware or automated checks were unavailable instead of claiming a pass.

## 9. Pull request checklist

- [ ] The issue, hardware assumptions, and changed behavior are documented.
- [ ] Applicable formatting, compiler checks, and tests pass.
- [ ] Sensor failures, timing, memory limits, and reconnect behavior are covered.
- [ ] Event identity, timestamp ownership, and quality match the shared contract.
- [ ] Configuration examples and build or flash instructions are updated.
- [ ] Validation evidence names the hardware and any untested limitations.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
