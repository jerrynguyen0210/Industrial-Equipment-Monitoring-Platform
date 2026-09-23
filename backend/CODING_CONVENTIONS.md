# Backend Coding Conventions

Development rules for telemetry ingestion, persistence, APIs, and equipment
monitoring. Read this guide before adding or changing backend code.

The backend currently provides a FastAPI health API backed by PostgreSQL. See
[README.md](README.md) for the Python toolchain and executable checks. The wider
domain, security, and reliability rules below remain implementation expectations.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests. Keep each change focused on its issue and acceptance criteria.
- Follow [.editorconfig](../.editorconfig): UTF-8, LF line endings, a final
  newline, and spaces. Default indentation is two spaces; Python uses four.
- Keep backend setup and validation commands in [README.md](README.md).
- Keep shared API schemas, telemetry contracts, and architecture decisions in
  [docs/](../docs/README.md). Update them with changes to observable behavior.
- Record significant departures from this guide in the pull request. Changes to
  shared contracts or architecture also need a documented decision in `docs/`.

## 2. Code style and maintainability

- Use the chosen language's naming and typing conventions consistently. Add a
  formatter, linter, and applicable type checks with the first implementation;
  use the same configuration locally and in CI.
- Name functions with verbs and types with domain nouns, such as equipment,
  telemetry, and alert. Prefer specific names over `data`, `manager`, or `utils`.
- Keep functions focused on one responsibility. Separate parsing, validation,
  business decisions, and persistence when they have distinct behavior.
- Make inputs, outputs, and failure cases explicit. Prefer typed models where
  supported; validate external data at runtime even when static types exist.
- Use named constants or configuration for units, limits, and thresholds. Avoid
  unexplained numbers and hidden changes to shared mutable state.
- Comment on reasons, constraints, and tradeoffs. Remove dead code and unused
  imports; do not retain commented-out implementations.
- Link TODOs to an issue and describe the missing behavior. Do not leave silent
  placeholders on a production execution path.
- Introduce abstractions when they clarify a boundary or remove meaningful
  duplication. Avoid speculative frameworks and unnecessary dependencies.

## 3. Responsibilities and dependencies

Organize modules by capability, keeping these responsibilities distinct. They
can live in one deployable service; separate services are not required.

| Responsibility | Owns |
| --- | --- |
| Transport adapters | HTTP routes or message consumers, parsing, and response mapping. |
| Application services | Use cases, authorization decisions, and transaction coordination. |
| Domain logic | Equipment state, telemetry interpretation, and monitoring rules. |
| Infrastructure adapters | Database queries, broker clients, and external service calls. |

- Keep business decisions out of route handlers and database callbacks.
- Keep domain logic independent of HTTP, broker, and database frameworks.
- Pass dependencies explicitly so clocks, storage, and external services can be
  substituted in tests. Avoid global service instances with hidden state.
- Return explicit response models. Do not expose database entities or internal
  fields directly through the API.
- Keep shared modules small and purposeful. Share contracts across workstreams
  through documented schemas rather than importing backend internals.

## 4. Telemetry integrity and equipment state

- Define a versioned telemetry contract before integrating with the gateway or
  simulator. Specify required fields, identifiers, timestamp format, metrics,
  units, quality indicators, size limits, and compatibility rules.
- Distinguish when a device measured a value from when the backend received it.
  Store instants in UTC and use an explicit timezone in serialized timestamps.
- Define acceptable clock skew, future timestamps, and late-arrival behavior.
  Do not silently replace device timestamps with receipt timestamps.
- Treat retries and duplicate delivery as expected. Define a stable event key
  and deduplication scope shared with the gateway; enforce uniqueness atomically
  rather than relying on an in-memory check or a read before an insert.
- Define how out-of-order readings affect history, current state, and alerts.
  An older reading must not overwrite newer current state without an explicit
  rule. Define tie-breaking for equal timestamps.
- Validate finite numeric values, units, supported metrics, and equipment
  identity. Distinguish missing, null, invalid, and zero values.
- Specify whether invalid readings are rejected or retained with quality flags.
  Never silently clamp or discard values without a documented policy.
- Define freshness and offline thresholds. Missing telemetry must not imply a
  zero reading or healthy equipment.
- Make alert rules explicit about evaluation windows, boundary values, repeated
  readings, hysteresis or debounce, and recovery. Reprocessing an event must not
  create duplicate alert transitions or notifications.

## 5. API and message contracts

- Document request and response schemas, authentication requirements, errors,
  examples, and compatibility policy before other workstreams depend on them.
  Use an API schema format appropriate to the selected protocol.
- Use consistent field names and stable identifiers. Specify timestamp and unit
  conventions and whether fields are optional, nullable, or defaulted.
- For HTTP APIs, use methods and status codes consistently. Do not report a
  failed operation as a successful response containing an error message.
- Use a stable error shape with a machine-readable code, a safe message, and a
  request or correlation ID. Include validation details only when safe.
- Bound list sizes, telemetry query time ranges, and batch sizes. Provide
  pagination with deterministic ordering and a documented maximum page size.
- Define idempotency and concurrent-update behavior for mutations. Specify the
  handling of an idempotency key reused with different content.
- Document batch atomicity and partial failures so a caller knows what to retry.
- Prefer compatible additions. Coordinate breaking schema changes with affected
  workstreams and document migration and deprecation steps before rollout.

## 6. Persistence and migrations

- Use version-controlled migrations for schema changes. Do not rely on manual
  production edits or automatic development schema synchronization.
- Enforce applicable uniqueness, relationships, and required values in the
  database as well as in application validation.
- Use parameterized queries or safe query-builder bindings. Allowlist dynamic
  sort fields and identifiers; never concatenate untrusted query fragments.
- Define transaction boundaries around complete business operations. Keep
  transactions short and avoid network calls while holding database locks.
- Handle concurrent writes using database guarantees appropriate to the use
  case; an application-level existence check alone is insufficient.
- If a database update and event publication must succeed together, use a
  documented reliable delivery mechanism, such as a transactional outbox.
- Design indexes around actual query patterns. Review query plans and avoid
  unbounded scans, result sets, and one query per returned record.
- Define telemetry retention, aggregation, and deletion policies before storing
  production volumes. Document what happens to history when equipment is removed.
- Test migrations against representative existing data. For destructive changes,
  document backup, restore or forward-recovery steps and compatibility with the
  application versions involved in deployment.

## 7. Security and configuration

- Authenticate callers and devices at entry points. Authorize each operation
  against the requested equipment or resource; a supplied ID is not proof of
  access. If tenancy is introduced, enforce its boundary on every data path.
- Validate all external inputs, including gateway messages, query parameters,
  headers, and configuration. Bound payload sizes, nesting, and processing work.
- Keep credentials and tokens out of source code, fixtures, logs, and examples.
  Commit sanitized `.env.example` files listing required settings.
- Validate configuration at startup and fail clearly when required settings are
  missing. Do not use development credentials or insecure production fallbacks.
- Give database and service accounts only the permissions they need. Use
  encrypted transport for deployed connections carrying sensitive data or
  credentials, and document credential provisioning and rotation.
- Restrict cross-origin access to intended clients when HTTP browser access is
  introduced. Keep development exceptions explicit and environment-specific.
- Pin dependencies through the selected package manager's lockfile. Review new
  dependencies for necessity, maintenance, licensing, and known vulnerabilities.
- Audit security-sensitive and configuration-changing actions with actor,
  action, target, time, and outcome, while excluding secrets and sensitive payloads.

## 8. Failures, delivery, and resource limits

- Distinguish validation failures, access failures, conflicts, and transient
  infrastructure failures. Map them consistently to API or consumer behavior.
- Do not swallow exceptions or report success before the documented durability
  boundary. Acknowledge telemetry only after durable storage or durable handoff;
  document which guarantee the caller receives.
- Set timeouts for external calls. Retry only eligible transient failures with
  bounded attempts, backoff, and jitter; require idempotency for retried effects.
- Bound queues, worker concurrency, connection pools, and memory use. Apply
  backpressure or an explicit overload response when capacity is exhausted.
- Define how malformed or repeatedly failing messages are quarantined, observed,
  and replayed without infinite retry loops or duplicate effects.
- Support graceful shutdown: stop accepting new work, drain within a timeout,
  and preserve or release unfinished work so it can be retried safely.
- Handle partial dependency outages deliberately. Document whether an operation
  fails, queues work, or serves stale data, including how staleness is exposed.

## 9. Observability and operations

- Emit structured logs with severity, operation, outcome, and correlation ID.
  Propagate correlation across incoming requests, messages, and downstream calls.
- Log enough context to investigate failures without dumping full telemetry,
  credentials, or personal information. Avoid logging the same exception at
  every layer.
- Measure request latency, error rates, ingestion lag, rejected and duplicate
  events, queue depth, and alert-processing delay as those capabilities arrive.
- Keep metric labels bounded. Put event IDs and other unbounded identifiers in
  logs or traces rather than metric labels.
- Distinguish liveness from readiness. A temporary database outage should not
  automatically cause a liveness restart loop; readiness should reflect whether
  the instance can perform its documented role.
- Document deployment, migration order, recovery, and troubleshooting in
  `docs/` and `infra/`. State service limits and operational assumptions.

## 10. Testing and validation

- Put backend unit and service tests alongside backend code. Put shared contract
  and end-to-end tests in [tests/](../tests/README.md).
- Test observable behavior and acceptance criteria. For bug fixes, add a
  regression test when the behavior can be exercised reliably.
- Cover relevant edge cases: invalid input, denied access, duplicate and
  out-of-order telemetry, clock skew, stale equipment, threshold boundaries,
  concurrent writes, and dependency timeouts.
- Use integration tests for database constraints, migrations, transactions, and
  broker delivery behavior. Mocks alone cannot verify these guarantees.
- Keep tests deterministic: control clocks and random seeds, isolate test data,
  clean up resources, and avoid live production services and arbitrary sleeps.
- Use sanitized simulator fixtures for shared scenarios. Verify contracts from
  both producer and consumer perspectives when changing shared schemas.
- Run the relevant formatter, linter, type checks, and test suites once available.
  Record exact commands and results in the pull request. State missing checks
  honestly; do not claim unconfigured tooling has passed.
- Check realistic load and failure recovery for changes to high-volume ingestion
  or critical queries, using documented workloads and acceptance limits.

## 11. Pull request checklist

- [ ] The issue, scope, and acceptance criteria are clear.
- [ ] Code follows this guide and the configured automated checks pass.
- [ ] Relevant failure, security, concurrency, and telemetry edge cases are covered.
- [ ] API contracts, configuration examples, and setup instructions are updated.
- [ ] Database changes include migrations and a deployment and recovery plan.
- [ ] Logs and metrics support investigating the changed behavior safely.
- [ ] Validation results and any untested behavior or limitations are recorded.

Mark checklist items that do not apply, with a brief reason where useful. With
the first backend implementation, select and document the runtime, package
manager, data store, transport, supported versions, and executable setup and
validation commands in the backend README. Record significant choices in `docs/`.
