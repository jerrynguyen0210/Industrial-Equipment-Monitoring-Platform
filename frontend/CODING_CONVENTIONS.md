# Frontend Coding Conventions

Development rules for dashboards, telemetry history, and operator workflows.
These are implementation expectations; no frontend implementation or automated
checks are currently present.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep supported runtime versions, package manager, development, build, and test
  commands in [README.md](README.md), and commit the selected dependency lockfile.
- Follow the [project reference documents](../docs/README.md#project-reference-documents)
  for dashboard requirements and shared telemetry semantics. Record interface
  decisions in `docs/`; this guide does not finalize draft technology proposals.

## 2. Code style and component design

- Configure formatting, linting, and applicable type checks with the first
  implementation. Use consistent language and framework naming conventions.
- Organize by user-facing capability, such as equipment, history, and alerts.
  Separate reusable visual components from feature-specific data orchestration.
- Keep components focused and inputs explicit. Avoid hidden global dependencies
  and unnecessary abstractions around small, unrelated pieces of UI.
- For TypeScript, prefer explicit domain types and strict checks. Avoid unchecked
  casts and broad `any` types at API boundaries; validate uncertain data at runtime.
- Keep rendering free of network calls and state mutations. Put asynchronous
  work in the framework's supported lifecycle or data-loading mechanisms.
- Use stable domain identifiers for list keys. Keep derived values derived rather
  than maintaining several writable copies of the same state.
- Use shared design tokens for colors, spacing, and typography. Explain unusual
  interaction constraints in comments and link unfinished work to an issue.

## 3. API integration and state

- Centralize transport configuration, authentication integration, error mapping,
  and request cancellation. Do not scatter endpoint URLs across components.
- Model server data, temporary UI state, and editable form state separately.
  Include site, device, filters, and time range in relevant cache identities.
- Cancel obsolete requests or ignore stale responses. A slow response for a
  previously selected device must not replace the current device's view.
- Clear protected cached data on logout or account change. Revalidate data when
  access changes; never display another site's records from an overly broad cache.
- Clean up polling timers, subscriptions, and event listeners on unmount. Bound
  retry frequency and recover predictably after connection loss.
- Retry reads according to a bounded policy. Do not blindly replay mutations;
  follow backend idempotency and conflict semantics for each action.
- Show pending and failed saves explicitly. Use optimistic updates only when the
  operation has a reliable reconciliation and rollback strategy.

## 4. Telemetry and status presentation

- Show the device, value, unit, reading age, connection state, and active alert
  count as required. Render missing data as unavailable, never as zero or healthy.
- Distinguish the latest measurement, request refresh time, and connection status.
  A successful refresh or historical replay does not prove that a device is live.
- Use backend-authoritative equipment and alert state. Do not create a second
  alert engine in the browser or infer recovery from missing readings.
- Display the selected timezone explicitly. Preserve UTC instants at the API
  boundary and format them for display without losing their timezone meaning.
- Use trustworthy measurement time for history. Distinguish uncertain or missing
  timestamps; do not label backend receipt time as physical measurement time.
- Show gaps in charts. Do not interpolate missing readings or join disconnected
  segments in ways that imply continuous valid measurements.
- Label units, aggregation intervals, time ranges, and downsampling. Respect the
  API's bounded-query contract rather than fetching all raw telemetry to the client.
- Keep alert condition and acknowledgement separate. Acknowledging an active
  alert records the user's action; it does not resolve the temperature condition.

## 5. Interaction and accessibility

- Prefer semantic HTML and native controls with accessible names. Associate
  labels, descriptions, and validation errors with their form inputs.
- Make core workflows usable with a keyboard. Preserve visible focus and logical
  navigation order, and restore focus after closing dialogs.
- Use text or icons as well as color for status and severity. Provide readable
  contrast, responsive layouts, and support for zoom and reduced motion.
- Provide an accessible summary or tabular alternative for important chart data.
  Tooltips alone must not be the only way to inspect readings.
- Keep live updates understandable without repeatedly moving focus or announcing
  every telemetry point. Announce meaningful action outcomes and errors.
- Distinguish loading, empty, filtered-empty, stale, permission-denied, and failed
  states. Explain the next useful action using concise user-facing language.
- Validate forms for quick feedback while treating backend validation as
  authoritative. Preserve user input when a save fails where practical.
- Name consequential actions clearly and request confirmation when their impact
  warrants it. Disable or guard repeated submissions while an action is pending.

## 6. Security and configuration

- Treat all values shipped to the browser as public, including build-time
  configuration. Never embed backend secrets or gateway credentials in the bundle.
- Follow the agreed authentication and session design. Do not introduce token
  storage or authentication flows independently of the backend contract.
- Render external text through safe framework mechanisms. Avoid raw HTML; when
  required, use an explicit sanitization policy and review the content boundary.
- Present controls appropriate to the user's role and site, while relying on
  backend authorization for every protected action and resource.
- Handle expired sessions and denied access without leaking protected content,
  stack traces, or credentials. Prevent unbounded authentication retry loops.
- Keep secrets and personal or operational payloads out of analytics, client
  logs, URLs, and error reports. Use sanitized configuration examples.

## 7. Performance and diagnostics

- Bound rendered rows and chart points. Use pagination, aggregation, or measured
  rendering optimizations as datasets grow.
- Avoid one request per table row and unnecessary full-dashboard refetches. Share
  compatible requests and refresh only data affected by a mutation.
- Measure production builds with representative devices and telemetry volumes.
  Record the workload when assessing dashboard freshness and interaction latency.
- Distinguish frontend rendering delays from API and ingestion delays. Preserve
  correlation IDs from API errors for troubleshooting without exposing internals.
- Handle unexpected rendering failures with a useful recovery state. Do not hide
  repeated failures behind an endless loading indicator.

## 8. Testing and validation

- Keep component and frontend unit tests within `frontend/`; put shared workflows
  in [tests/](../tests/README.md).
- Assert visible behavior, keyboard interaction, and accessible control names.
  Avoid coupling every test to internal component structure or CSS classes.
- Cover missing and stale readings, chart gaps, timezone formatting, session
  expiry, denied access, failed saves, and out-of-order request completion.
- Verify alert acknowledgement separately from condition recovery. Exercise
  representative API contracts as well as mocked component states.
- Review responsive layouts and supported browser behavior. Automated checks
  complement keyboard and visual review; they do not replace them.
- Record exact build, type-check, lint, and test commands once tooling exists.
  State unavailable checks and remaining limitations honestly.

## 9. Pull request checklist

- [ ] The issue and observable UI behavior are clear.
- [ ] Applicable formatting, lint, type, build, and behavior checks pass.
- [ ] Loading, empty, stale, error, and permission states are handled.
- [ ] Telemetry units, timestamps, connection state, and alerts are represented correctly.
- [ ] Keyboard access, focus, responsive layout, and chart alternatives were reviewed.
- [ ] API contracts, setup instructions, and validation evidence are updated.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
