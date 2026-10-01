# Telemetry ingestion API

`POST /api/v1/telemetry/batches` accepts authenticated `telemetry-batch.v1`
requests. The generated [OpenAPI document](telemetry-openapi.json) contains full
schemas and examples.

## Authentication and ownership

1. Configure `GATEWAY_CREDENTIALS_JSON` as a JSON map from registered gateway IDs
   to unique bearer tokens.
2. Send the matching token as `Authorization: Bearer <token>`.
3. Restart the backend after adding, rotating, or revoking a token.

Missing or bad credentials return 401 `invalid_gateway_credential`. An unknown or
disabled gateway/site returns 403 `gateway_not_authorized`. Tokens are checked
before request parsing or database access. Payload fields cannot establish the
gateway identity.

For each item, an unregistered device returns `unknown_device`; a device assigned
elsewhere or disabled returns `wrong_gateway`. Ingestion locks registry rows until
commit so concurrent ownership changes cannot authorize stale data.

This runtime token map is a lab mechanism. It has no expiry or management API;
deployed credential traffic requires HTTPS and managed rotation.

## Request rules

```json
{
  "schema_version": 1,
  "events": [
    {
      "device_id": "esp-nano",
      "boot_id": "boot-1",
      "sequence_number": 0,
      "measured_at": "2026-10-01T01:10:00Z",
      "device_uptime_ms": 5000,
      "gateway_received_at": "2026-10-01T01:10:01Z",
      "metric": "temperature",
      "value": 24.6,
      "unit": "celsius",
      "quality": {"reading": "valid", "clock": "synchronised"}
    }
  ]
}
```

- A batch contains 1–500 events.
- IDs are nonempty, case-sensitive, at most 128 characters, and contain no NUL.
- Counters are integers from 0 through `9223372036854775807`.
- `metric` is `temperature`; `unit` is `celsius`.
- `value` is a finite JSON number. Negative and zero values are valid.
- `measured_at` is required but may be null. Absolute timestamps require RFC 3339
  with a timezone and are normalized to UTC.
- Clock quality is `synchronised`, `unsynchronised`, `estimated`, or `unknown`.
- All fields are explicit; unknown fields and duplicate JSON keys are rejected.
- Clients cannot send `backend_received_at`, `gateway_id`, or `site_id`.

The custom parser preserves decimal precision and validates events independently.
Do not replace it with a normal nested FastAPI body model: one invalid event would
then reject valid neighbors before per-item classification.

## Outcomes and transactions

HTTP 200 contains one ordered result per input:

| Outcome | Meaning |
| --- | --- |
| `accepted` | New row committed. |
| `duplicate` | Identity and immutable content match an existing row. |
| `rejected` | Permanent item failure with a stable reason. |

Identity is `(device_id, boot_id, sequence_number)`. PostgreSQL arbitrates
concurrent inserts. A retry compares schema, identity, measurement time, uptime,
metric, value, unit, and quality. Receipt times and batch metadata are excluded.
Changed immutable content returns `identity_conflict` without modifying the row.

Valid and permanently rejected items share one transaction. Savepoints isolate
data representation errors so a bad item does not roll back valid neighbors.
Results are returned only after commit.

Database, pool, lock, or commit failure returns 503 `ingestion_unavailable` with
no item results. When a commit result is uncertain, retry the unchanged batch;
committed rows become duplicates.

## Request-level errors

Envelope errors return HTTP 400:

| Reason | Condition |
| --- | --- |
| `malformed_batch` | Invalid UTF-8/JSON, duplicate keys, wrong structure/types, missing/extra fields, or empty events. |
| `unsupported_schema_version` | Integer version other than 1. |
| `batch_too_large` | More than 500 events. |

Structural errors take precedence, then version, then size. Error details contain
locations and codes without echoing submitted values.

Inside a valid envelope, a malformed event returns `malformed_value`; unsupported
metric takes precedence over unsupported unit. A malformed identity may contain
null identity fields in its result, so clients correlate it by array position.

## Regenerate and verify

From `backend/`:

```sh
python -m app.telemetry_openapi --output ../docs/telemetry-openapi.json
python -m unittest discover -s tests -v
```

Run the PostgreSQL ingestion suite from
[backend/README.md](../backend/README.md#run-the-checks) to test ownership,
concurrency, retries, conflicts, and commit failures.
