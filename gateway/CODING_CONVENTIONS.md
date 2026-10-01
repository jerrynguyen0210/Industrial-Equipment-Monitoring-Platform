# Gateway coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these C++17 rules.

## Code and boundaries

- Use RAII for SQLite, MQTT, HTTP, threads, and file handles.
- Keep config, intake validation, queue storage, HTTP transport, and response
  classification in separate modules.
- Use deterministic shutdown; stop callbacks and workers before closing storage.
- Format with clang-format 18 and build without ignored warnings.

## Durable delivery

- Validate topic and payload before storage, without logging payloads.
- Capture gateway receipt time at callback entry.
- Commit original event bytes to SQLite before acknowledging local storage.
- Forward only persisted rows; never bypass the queue.
- Claim/release rows transactionally and keep network calls outside transactions.
- Delete rows only after complete, ordered, committed backend outcomes.
- Quarantine permanent rejection; retry transport and service failures with
  bounded jittered backoff.
- Preserve identity and receipt time across retries and restarts.

## Configuration and security

- Require an explicit config path and reject unknown/duplicate settings.
- Keep MQTT and API credentials separate and out of logs.
- Use owner-only permissions for new queue and secret files.
- Bound payload, batch, connection, response, and shutdown time.
- Require MQTT TLS outside a trusted lab; verify HTTPS certificates and names.

## Validation checklist

- [ ] Format, Release build, and CTest pass.
- [ ] Tests cover bad config, MQTT validation, duplicate/conflict, queue recovery,
  mixed outcomes, malformed responses, outage recovery, and shutdown.
- [ ] No success log precedes its durability boundary.
- [ ] Queue migration and backup behavior are documented.
