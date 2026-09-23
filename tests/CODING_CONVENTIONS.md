# Shared Testing Coding Conventions

Development rules for contract, integration, end-to-end, reliability, and
acceptance tests spanning workstreams. These are implementation expectations;
no shared test runner or automated suite is currently configured.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep runner versions, dependencies, setup, execution, and cleanup commands in
  [README.md](README.md).
- Keep unit and single-workstream service tests beside their implementation.
  Use `tests/` for shared contracts, fixtures, and workflows across boundaries.
- Trace tests to issues, acceptance criteria, and the
  [project reference documents](../docs/README.md#project-reference-documents).
  Draft requirements are a documented baseline, not evidence of a passing release.
- Follow approved contract decisions when they resolve older open questions.
  Explicitly track unresolved behavior rather than choosing an expectation silently.

## 2. Test code and organization

- Configure formatting, linting, and applicable type checks for test code too.
  Group suites by contract or scenario and label required services or hardware.
- Name tests by observable behavior and condition, such as keeping one stored
  record when a committed event is retried after its response is lost.
- Keep arrange, action, and assertions easy to distinguish. Limit each test to a
  coherent behavior with enough diagnostics to understand a failure.
- Prefer public interfaces and observable outcomes. Use targeted internal probes
  only when needed to verify a commit, durable queue, or controlled failure boundary.
- Keep helpers focused on setup and common actions. Avoid hiding the expected
  behavior in a large helper or reimplementing production algorithms in the test.
- Test meaningful invariants and failure cases. Coverage percentages alone do not
  prove correctness, and snapshots alone do not verify behavior.

## 3. Isolation, fixtures, and determinism

- Give each run isolated device IDs, credentials, storage, and resource names.
  Tests must be order-independent and safe to execute concurrently when enabled.
- Use disposable environments. Never default tests, migrations, cleanup, or load
  generators to production services or live equipment.
- Seed fixtures explicitly and keep them small, synthetic, and free of secrets.
  Record fixture schema versions and the requirements they exercise.
- Control clocks and random seeds for deterministic logic checks. Record real
  clocks, synchronization assumptions, and network conditions for timing tests.
- Poll for an observable condition with a deadline rather than using arbitrary
  sleeps. On timeout, report the last observed state and relevant diagnostics.
- Clean up owned resources even after assertion failure. Preserve useful failure
  evidence before teardown and never delete unrelated resources.
- Use the [simulator guide](../simulator/CODING_CONVENTIONS.md) for reproducible
  traffic and faults; expected outcomes must come from contracts and requirements.

## 4. Contract and ingestion verification

- Turn the approved F01-F07 contract examples into executable shared fixtures:
  valid, matching duplicate, conflicting duplicate, invalid, mixed, batch boundary,
  and commit-then-lost-response cases.
- Verify `(device_id, boot_id, sequence_number)` identity and immutable-content
  comparisons. Matching retries keep one row; conflicts preserve the original row.
- Verify timestamp ownership and quality semantics. Gateway receipt time survives
  retries; backend receipt time is server-generated; uncertain measurement time
  must not silently become a trusted historical timestamp.
- Verify the v1 envelope and 1-to-500 event limit. Test missing, empty, malformed,
  unsupported-version, and oversized requests with their documented outcomes.
- For a mixed batch, assert each item's outcome, stored data, and gateway queue or
  quarantine transition. HTTP 200 alone is not a sufficient assertion.
- Verify that `accepted` follows database commit. Exercise commit failure and
  actual commit followed by interrupted response as distinct scenarios.
- Exercise actual database uniqueness and concurrent delivery. Mocks cannot prove
  atomic deduplication or transaction behavior.
- Cover incomplete or contradictory responses so the gateway cannot silently
  delete unconfirmed events. Track any missing response-mapping specification.

## 5. End-to-end and reliability scenarios

Maintain traceability to the baseline acceptance scenarios as they are implemented.
Mark unavailable dependencies or unresolved semantics explicitly.

| Scenarios | Required evidence |
| --- | --- |
| AT-01: real reading | Correct device, temperature, unit, and timestamp reach the dashboard from hardware. |
| AT-02: alert lifecycle | One episode opens, acknowledgement is retained, and recovery resolves its condition. |
| AT-03 and AT-04: outage and restart | Local MQTT remains available, committed queue data survives, and recovery forwards it. |
| AT-05: lost response | Commit succeeds, response is interrupted, retry is a duplicate, and one row remains. |
| AT-06: mixed batch | Valid, duplicate, and invalid items receive independent correct outcomes. |
| AT-07: access control | Cross-site access and unauthorized acknowledgement fail without changing data. |
| AT-08: historical replay | A stopped device becomes offline even while old telemetry is replayed. |
| AT-09: storage limit | Queued data is preserved and rejected new intake is measurable. |
| AT-10: deployment and restore | Clean-checkout deployment and isolated backup restoration produce a working system. |

- Compare known event identities and payloads across generated, committed, queued,
  quarantined, and stored data. Equal row counts alone can hide loss and corruption.
- State the durability boundary: restart recovery covers events committed to the
  gateway queue. Do not claim coverage for earlier losses or untested power failure.
- Test real sensor behavior on hardware and classify simulator-only runs clearly.
- Verify duplicate and out-of-order events do not incorrectly advance live alerts.
  Keep cross-boot ordering and exact stale/gap calculations tied to their pending
  decisions before claiming full alert-engine acceptance.
- Distinguish active or resolved condition from acknowledged or unacknowledged
  status. Missing telemetry is not evidence of temperature recovery.

## 6. Security and user-facing verification

- Verify role and site authorization through backend requests as well as UI
  behavior. Hidden controls alone do not prove that an operation is forbidden.
- Cover missing, expired, and revoked credentials, wrong-gateway device ownership,
  viewer writes, cross-site identifiers, and unauthorized MQTT topics.
- Exercise oversized and malformed input, certificate rejection, and safe error
  reporting. Ensure logs and captured evidence exclude credentials and secrets.
- Verify core dashboard workflows with a keyboard, explicit status text or icons,
  and visible loading, empty, stale, permission-denied, and failed states.
- Check chart gaps, units, timezones, and alert acknowledgement using representative
  data rather than only empty or ideal dashboard fixtures.

## 7. Performance and operational evidence

- Reference the applicable NFR target and record hardware, versions, dataset,
  concurrency, duration, network conditions, and actual measured results.
- Define latency start and end points. Cross-host timing requires synchronized
  clocks or a measurement design that does not depend on clock agreement.
- Report latency distributions, throughput, errors, and unconfirmed events. Do
  not claim success by averaging away failed or unfinished work.
- Distinguish load-generator limits from platform capacity. Verify final stored
  identities after backlog drain rather than counting successful sends alone.
- Measure restore duration and restored data in an isolated environment. A backup
  file's existence or a container reaching running state is insufficient.
- Keep routine checks bounded and reproducible. Run longer load and hardware
  campaigns according to the change's risk and release criteria.

## 8. CI, failures, and reporting

- Separate fast checks from integration, hardware, and long-running acceptance
  suites. Document prerequisites and the trigger for each once CI exists.
- Use nonzero exit codes for failed assertions. Report passed, failed, skipped,
  blocked, and not-run cases distinctly; do not count missing coverage as success.
- Retain sanitized logs, seeds, fixture versions, service versions, and correlation
  IDs needed to reproduce failures. Bound artifact size and retention.
- Treat intermittent failures as defects. If temporarily quarantining a flaky test,
  record its owner, issue, impact, and restoration criteria; do not silently disable it.
- Do not retry an entire failed suite until it turns green without retaining and
  reporting the original failure. Use retries only where the test's design requires them.
- Record exact commands and results in the pull request. A documentation-only
  change normally needs documentation checks, not new executable tests.

## 9. Pull request checklist

- [ ] Tests trace to issues, approved contracts, or explicit acceptance criteria.
- [ ] Fixtures, clocks, seeds, and resources are reproducible and isolated.
- [ ] Assertions verify outcomes and relevant persistence or failure boundaries.
- [ ] Shared scenarios cover the affected producer and consumer responsibilities.
- [ ] Cleanup, failure diagnostics, and evidence avoid data loss or secret exposure.
- [ ] Commands, results, skipped checks, open decisions, and limitations are recorded.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
