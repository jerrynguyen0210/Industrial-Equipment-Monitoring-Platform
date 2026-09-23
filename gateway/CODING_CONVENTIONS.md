# Gateway Coding Conventions

Development rules for device connectivity, durable edge buffering, protocol
translation, and backend forwarding. These are implementation expectations;
no gateway implementation or automated checks are currently present.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep supported hardware, runtime versions, installation, migration, run, and
  test commands in [README.md](README.md).
- Follow the [project reference documents](../docs/README.md#project-reference-documents),
  especially the approved ingestion contract. This guide does not finalize draft
  architecture proposals or resolve their remaining queue and retry decisions.
- Document device-to-gateway and gateway-to-backend interfaces in `docs/` and
  coordinate changes with firmware, simulator, backend, and tests.

## 2. Code style and responsibilities

- Configure formatting, compiler or type checks, and linting with the first
  implementation. Use consistent language conventions and explicit error handling.
- Separate protocol adapters, envelope validation, durable queue storage,
  forwarding, and configuration. Keep backend business rules out of the gateway.
- Keep transport callbacks short. Bound parsing and persistence work and move
  long-running forwarding outside the MQTT callback path.
- Inject clocks, storage, and network clients so failure and recovery behavior can
  be exercised deterministically. Avoid global mutable connection state.
- For C++, use clear ownership and RAII for resources, checked numeric conversions,
  and bounded buffers. Do not share database handles or client instances across
  threads unless their concurrency contract permits it.
- Express units in names and configuration. Link TODOs and unusual protocol
  workarounds to issues explaining their lifecycle.

## 3. Contract boundaries and event identity

- Preserve `(device_id, boot_id, sequence_number)` and immutable device content
  through buffering, batching, retries, and restarts. Retries are not new events.
- Assign `gateway_received_at` at original receipt and retain it across retries.
  Do not overwrite `measured_at`, `device_uptime_ms`, or clock quality.
- Do not supply `backend_received_at`; the backend owns it. Use UTC for persisted
  absolute timestamps and monotonic time for in-process retry intervals.
- Validate minimum envelope shape, schema compatibility, size, and field types
  before queueing. Preserve failure diagnostics without logging whole payloads.
- Do not silently correct invalid units or substitute fabricated values. Any
  normalization must be explicit in the shared contract.
- Use authenticated device/topic mappings when available. Treat backend ownership
  validation as authoritative; payload site or gateway IDs cannot grant access.

## 4. Durable queue and concurrency

- Persist an event before making it eligible for forwarding. The recovery guarantee
  starts when gateway storage commits, not when MQTT acknowledges receipt.
- Document storage transaction boundaries and durability settings on the actual
  gateway hardware. Test process restart separately from power-loss behavior.
- Define queue states and transitions explicitly. If work is claimed or leased by
  a worker, make claims atomic and recover abandoned work after a restart.
- Preserve unsent records during schema migrations and service upgrades. Document
  queue backup, corruption diagnosis, and recovery procedures.
- Bound queue and quarantine storage. At the delivery-queue limit, preserve queued
  events, reject new intake visibly, and increment a loss counter; never silently
  overwrite the oldest unconfirmed data.
- Make quarantine writes and delivery-queue removal atomic or recoverable so a
  crash cannot erase a rejected event without a diagnostic record.
- Keep database transactions short and outside network calls. Define how intake
  and forwarding coordinate without starving either path.
- Record storage usage and write pressure. Do not trade away the declared recovery
  guarantee by silently weakening persistence settings for performance.

## 5. Batching and response handling

- Use the approved `POST /api/v1/telemetry/batches` contract with
  `schema_version = 1` and between 1 and 500 events per request. Also bound encoded
  request bytes and batch waiting time.
- Authenticate using the gateway's own credential. The backend derives gateway
  identity from that credential and validates device assignments.
- Match each response item to its submitted event. Do not infer success for the
  entire batch from HTTP 200; a successful request may contain mixed outcomes.

| Outcome or failure | Queue action |
| --- | --- |
| `accepted` | Remove the confirmed event; acceptance means backend commit succeeded. |
| `duplicate` | Remove the confirmed matching event; the authoritative row already exists. |
| `rejected` with a permanent reason | Move the event to bounded quarantine with its reason. |
| Timeout, connection failure, HTTP 429, or 5xx | Retain unconfirmed events and retry with bounded backoff. |
| HTTP 401 or 403 | Retain events, surface the credential problem, and avoid rapid retries. |
| HTTP 400 or an unsupported response | Retain unconfirmed events and diagnose the contract or request failure. |

- Validate response completeness and consistency before destructive queue changes.
  Missing, unknown, or contradictory outcomes must not cause unconfirmed deletion.
- For malformed items without usable identity or ambiguous response mapping, track
  the contract question and preserve data rather than guessing which row to remove.
- Handle `identity_conflict` as a rejection; never relabel it a matching duplicate
  or generate a new identity to bypass the conflict.
- A lost response after backend commit is expected to cause a retry with identical
  event content and a `duplicate` result. Do not claim exactly-once transport.

## 6. Retry, outage, and lifecycle behavior

- Use bounded exponential backoff with jitter and explicit network timeouts.
  Respect applicable server retry guidance while keeping attempts rate-limited.
- Decide and document timing parameters; their exact values remain an open
  implementation decision in the source documents.
- Keep unconfirmed data durable when automatic retries are suspended. Attempt
  limits must not silently discard valid events.
- Keep local MQTT intake and persistence operational during backend outages.
  Isolate forwarding failure from the local acquisition path.
- Drain backlog while continuing to accept new readings within capacity. Measure
  both catch-up throughput and the age of the oldest queued event.
- Stop accepting work deliberately during shutdown, finish or release claims, and
  leave unfinished events recoverable. Bound the shutdown wait.
- Define heartbeat handling separately from replay. Old readings must not be
  presented as proof of a current device connection.

## 7. Security, configuration, and diagnostics

- Keep credentials out of source, logs, queue diagnostics, and fixtures. Use
  sanitized examples and validate configuration at startup.
- Verify TLS peer identity for deployed MQTT and HTTPS connections. Document
  credential rotation and revocation without deleting queued telemetry.
- Restrict broker permissions, local queue-file access, and service privileges.
  Device credentials must not confer gateway or administrator permissions.
- Emit structured logs with operation, event identity where useful, outcome, and
  correlation information. Redact credentials and bound repetitive failure logs.
- Expose queue depth, oldest-event age, intake loss, quarantine counts, retry
  counts, forwarding rates, storage usage, and service health.
- Separate local readiness from backend reachability. Report a backend outage
  without causing a restart loop that disrupts healthy local collection.

## 8. Testing and validation

- Keep queue, adapter, and retry tests within `gateway/`; put shared ingestion and
  end-to-end scenarios in [tests/](../tests/README.md).
- Test actual storage persistence, migration, concurrency, and restart recovery.
  An in-memory fake cannot establish durable-queue guarantees.
- Cover mixed outcomes, matching and conflicting duplicates, lost responses,
  malformed responses, revoked credentials, rate limiting, and storage exhaustion.
- Verify backend-independent MQTT operation and automatic backlog recovery on
  declared hardware with recorded software versions and workloads.
- Use controlled clocks and failure injection for retry tests. Record exact
  commands and results, including missing checks and untested power-loss behavior.

## 9. Pull request checklist

- [ ] The issue, queue transitions, and contract changes are documented.
- [ ] Applicable formatting, compiler or type checks, and tests pass.
- [ ] Persistence-before-forwarding and retry identity are preserved.
- [ ] Per-item outcomes, partial failures, and lost responses are handled safely.
- [ ] Queue bounds, restart recovery, and outage diagnostics are verified.
- [ ] Setup, migration, recovery instructions, and validation evidence are updated.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
