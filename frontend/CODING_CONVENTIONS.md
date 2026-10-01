# Frontend coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these frontend-specific rules.

## Components and state

- Use typed function components and keep data fetching in focused hooks/services.
- Represent loading, empty, ready, stale, and error states explicitly.
- Cancel obsolete requests and polling timers on retry, dependency change, and
  unmount.
- Keep API response validation at the boundary; do not let invalid numbers or
  timestamps reach charts.
- Use stable keys and memoize only after measuring a real problem.

## Monitoring semantics

- Label stored reading time and source accurately.
- Never present an old reading or HTTP health response as proof of live equipment.
- Respect history `gap_before` and truncation instead of drawing invented data.
- Treat decimal strings as untrusted input and preserve unavailable states.
- Explain that online status is recent server contact, not fault diagnosis.

## Interaction and security

- Use semantic HTML, associated labels, keyboard access, visible focus, and
  announced errors.
- Ask for confirmation before deletion and report backend conflicts clearly.
- Never place device passwords, gateway tokens, or other secrets in source,
  browser storage, URLs, logs, or analytics.
- Only `VITE_*` values are public build configuration; assume users can read them.

## Validation checklist

- [ ] Prettier and TypeScript checks pass.
- [ ] Tests cover loading, empty, success, error, retry, timeout, and cleanup.
- [ ] Production build passes.
- [ ] Keyboard and narrow-screen workflows remain usable.
- [ ] User wording matches backend status and time semantics.
