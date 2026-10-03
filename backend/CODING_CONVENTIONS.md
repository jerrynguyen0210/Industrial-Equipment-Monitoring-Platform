# Backend coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these backend-specific rules.

## Structure

- Organize application code by feature under `devices`, `telemetry`, and `alerts`.
  History belongs to telemetry; shared configuration/authentication belongs to
  `core`, database infrastructure to `db`, and broker access to `integrations`.
- Keep HTTP parsing/mapping, authentication, business rules, and persistence in
  separate modules.
- Put request/response models in feature `schemas.py`, HTTP adapters in
  `router.py`, and business rules/transaction coordination in `service.py`.
- Device and telemetry repositories take a caller-owned session and never commit.
  Alert evaluation uses the ingestion session so alert state commits with readings.
- Import implementations from feature packages. Root compatibility modules exist
  only for deployment scripts and documented CLI commands.
- Use typed functions and explicit dependencies. Keep route handlers small.
- Format and lint with the committed Ruff configuration.
- Never expose database models directly as public request models.

## Telemetry and data

- Preserve `(device_id, boot_id, sequence_number)` as event identity.
- Parse JSON numbers without precision loss. Reject nonfinite values.
- Require timezone-aware datetimes and normalize them to UTC.
- Let PostgreSQL own `backend_received_at`; never trust a client value.
- Return outcomes only after commit. Preserve existing rows on duplicates and
  conflicts.
- Hold registry locks when ownership must stay stable through a write.

## APIs and security

- Use stable machine-readable error reasons and safe messages.
- Validate authentication before parsing protected request bodies.
- Do not log tokens, passwords, connection strings, request bodies, or raw
  exceptions containing submitted values.
- Keep health, request, response, and OpenAPI behavior synchronized.
- Bound batch size, query range, result count, and database timeouts.

## Migrations

- Change schema through Alembic; application startup never migrates or seeds.
- Make ownership, uniqueness, required values, and delete behavior database
  constraints where possible.
- Document destructive downgrade behavior and test it on disposable data.
- Review model and migration agreement before merge.

## Validation checklist

- [ ] Ruff lint and format checks pass.
- [ ] Unit tests cover success, invalid input, and dependency failure.
- [ ] PostgreSQL tests cover constraints, concurrency, transactions, and recovery.
- [ ] API docs and generated OpenAPI are current.
- [ ] Logs and errors contain no secrets or sensitive payloads.
