# Simulator Coding Conventions

Development rules for virtual devices, repeatable telemetry, fault injection,
and load scenarios. The API fixture sender and its executable checks are documented
in [README.md](README.md); broader device/load scenarios remain future work.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep runtime versions, configuration, scenario execution, and validation commands
  in [README.md](README.md). Commit sanitized, reproducible scenario inputs.
- Follow the [project reference documents](../docs/README.md#project-reference-documents),
  especially the approved telemetry contract and its F01-F07 examples.
- Simulated devices must follow the firmware contract. A simulator does not own
  backend validation, alert decisions, or unresolved protocol definitions.

## 2. Code style and structure

- Configure formatting, linting, and applicable type checks with the first
  implementation. Use consistent naming for devices, scenarios, clocks, and faults.
- Separate device models, event generation, scheduling, transport, and reporting.
  Keep scenario definitions independent of a particular network client.
- Use explicit configuration models and reject unknown or invalid values. Define
  units for rates, durations, temperature values, delays, and capacity limits.
- Inject clocks, random-number generators, and transports for deterministic tests.
  Avoid hidden globals and implicit reads of wall-clock time in scenario logic.
- Keep scenario files declarative; do not evaluate arbitrary code from inputs.
  Explain modeling assumptions and link TODOs or protocol gaps to issues.

## 3. Reproducibility and scenario definition

- Give each scenario a stable name, purpose, contract version, preconditions,
  device population, event schedule, termination condition, and expected outcomes.
- Record the random seed, configuration, simulator version, target, and run ID.
  The same seed, configuration, start time, and version must reproduce the same
  generated event sequence; network completion timing may still vary.
- Use independent seeded streams or deterministic scheduling for each device so
  thread timing does not accidentally change generated values.
- Distinguish virtual time from wall-clock time. Use virtual time for fast logic
  tests and real elapsed time for throughput and latency measurements.
- Make device and boot IDs reproducible within a scenario but isolated between
  independent runs. Reusing identities must be an intentional replay scenario.
- Specify whether timestamps are fixed or relative to a recorded run start. A
  fixed historical fixture must not accidentally serve as a live-alert test.

## 4. Telemetry identity, ownership, and transport modes

- Use `(device_id, boot_id, sequence_number)` as event identity. A simulated reboot
  gets a new boot ID; a retry keeps the original identity and immutable content.
- Generate valid MVP readings as finite `temperature` values in `celsius` within
  the declared sensor range, with approved reading and clock-quality values.
- Keep missing or untrustworthy measurement time explicit. Preserve
  `device_uptime_ms` and do not relabel receipt time as measurement time.
- Declare the boundary exercised by each mode. Device mode publishes the device
  contract through the gateway; an API-only mode deliberately bypasses that path.
- In device mode, leave `gateway_received_at` to the gateway. A simulated gateway
  mode owns the original gateway receipt time and preserves it across retries.
  Neither mode supplies `backend_received_at`.
- In API-only ingestion mode, use the approved batch envelope, credential, endpoint,
  and 1-to-500 event limit. Mark oversized or malformed batches as negative tests.
- Do not claim gateway durability or real sensor coverage from API-only success.

## 5. Normal, fault, and replay scenarios

- Keep normal scenarios contract-valid. Make invalid values, malformed envelopes,
  unsupported versions, and unauthorized identities explicit negative cases.
- Cover valid events, matching retries, conflicting identity reuse, invalid units,
  mixed results, the maximum batch boundary, and response loss after commit.
- Model missing telemetry, clock skew, reboot, connection loss, delayed delivery,
  and out-of-order replay separately so each failure has a clear expected result.
- Preserve payloads during delay or replay. To test a conflicting duplicate, change
  immutable content deliberately and expect `identity_conflict`.
- Define fault injection at a named boundary. A request timeout is not proof that
  a commit occurred; a commit-then-lost-response scenario needs controlled evidence
  of both the commit and the interrupted response.
- Keep live heartbeat behavior separate from historical replay. Replayed telemetry
  must not manufacture evidence that a stopped device is online.
- Do not invent disconnected-sensor payload fields or resolve open alert-ordering
  semantics in a fixture. Track those dependencies in the shared decision record.

## 6. Load generation and resource limits

- Specify device count, per-device rate, duration, ramp-up, batch size, concurrency,
  and payload size. Avoid unlimited generation or implicit infinite runs.
- Bound buffers and in-flight requests. Report when the generator cannot sustain
  its configured rate instead of silently slowing and declaring the target met.
- Measure scheduled, generated, sent, retried, confirmed, rejected, and dropped
  events separately. Retries must not inflate the count of unique generated events.
- Separate generator saturation, network delay, gateway delay, and backend delay
  when reporting performance. Record hardware and software versions.
- Stop predictably on cancellation, close clients, and report unsent or unconfirmed
  events. Do not report them as accepted merely because transmission started.
- Keep repeatable acceptance workloads distinct from exploratory stress runs.

## 7. Configuration and execution boundaries

- Default to local or isolated test targets. Require an explicit target and bounded
  workload for remote runs, and use dedicated test credentials and device IDs.
- Keep credentials outside scenario files, logs, fixtures, and reports. Commit
  examples with placeholders and document required environment settings.
- Scope setup and cleanup to the current test run's owned resources. Do not use
  broad database resets or topic deletion against shared environments.
- Identify simulated data in test metadata or registered test resources without
  adding unapproved fields to the wire contract.
- Make destructive fault injection opt-in and name the affected service or route.
  A scenario must not stop unrelated local services.

## 8. Reporting and validation

- Produce a run summary with seed, configuration, source revision, duration,
  actual throughput, failures, and unconfirmed counts. Use a nonzero exit code
  when an executable scenario's assertions fail.
- Report per-item backend outcomes rather than treating HTTP 200 as universal
  acceptance. Distinguish new accepted records from matching duplicates.
- Keep expected results independent of the system under test. Do not generate
  expected alert outcomes by invoking the same production alert evaluator.
- Unit-test generation, seeds, schedules, identity, encoding, and fault selection
  within `simulator/`. Put shared acceptance assertions in
  [tests/](../tests/README.md).
- Verify that a scenario can be replayed from its recorded inputs and that normal
  fixtures remain compatible with firmware and the approved ingestion contract.
- Document exact commands when tooling exists, and state missing assertions or
  unverified behavior rather than treating successful traffic generation as a pass.

## 9. Pull request checklist

- [ ] The issue, scenario purpose, target boundary, and expected outcomes are clear.
- [ ] Applicable formatting, lint or type checks, and tests pass.
- [ ] Seed, clock, IDs, configuration, and replay behavior are reproducible.
- [ ] Generated events and negative cases follow the shared contract deliberately.
- [ ] Workload limits, cleanup scope, and unconfirmed-event reporting are explicit.
- [ ] Scenario examples, run commands, and validation evidence are updated.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
