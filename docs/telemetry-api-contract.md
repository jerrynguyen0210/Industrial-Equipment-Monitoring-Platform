# Telemetry API validation contract

The backend implements the request/response models and reusable HTTP validation
for `telemetry-batch.v1`, following sections 3, 5, and 7 of the
[approved contract](Technical_Lead_Telemetry_Ingestion_Contract_Approval_Sprint01.pdf).
The [OpenAPI 3.1 document](telemetry-openapi.json) describes the planned
`POST /api/v1/telemetry/batches` operation, bearer authentication requirement,
schemas, valid/null-time/mixed request examples, mixed outcomes, and HTTP 400 errors.

This task does not mount the ingestion route. The running `/openapi.json` continues
to describe the health API. Authentication, registry checks, duplicate/conflict
classification, and commit orchestration must be connected before ingestion is
enabled. Validation never returns `accepted` or `duplicate` by itself.

## Models and field rules

Models live in `backend/app/telemetry_schemas.py`, separately from persistence
entities in `app.models`:

| Model | Purpose |
| --- | --- |
| `TelemetryQuality` | Required `reading: valid` and clock quality. |
| `TelemetryEvent` | Required event fields; client backend receipt-time overrides are forbidden. |
| `TelemetryBatch` | Integer `schema_version: 1` and 1 through 500 valid events. |
| `TelemetryResponseItem` | Identity, `accepted`/`duplicate`/`rejected`, and rejection reason. |
| `TelemetryBatchResponse` | Server-owned `batch_id` and ordered results. |
| `TelemetryBatchError` | Stable request reason, safe message, and field error details. |

- `metric` must be `temperature`; `unit` must be `celsius`.
- `value` must be a finite JSON number. Zero and negative temperatures are valid;
  strings, booleans, null, NaN, and infinities are not numbers in this contract.
  No sensor-specific range has been selected, so validation does not invent one.
  `value_out_of_range` remains available for that later domain check.
- IDs are nonempty, case-sensitive strings of at most 128 characters, preserved
  exactly. Boot IDs need not be UUIDs. Counters are integers from zero through
  `9223372036854775807`. These limits match the existing storage schema.
- `measured_at` is required but nullable for every approved clock quality:
  `synchronised`, `unsynchronised`, `estimated`, and `unknown`. A trustworthy
  historical time requires both a supplied timestamp and `synchronised` quality.
  The approval does not require synchronised clocks to supply a non-null time.
  Other qualities preserve supplied timestamps; validation never substitutes a
  receipt timestamp or treats uptime as wall-clock time.
- Absolute timestamps require RFC 3339 strings with `T` and an explicit timezone.
  UTC `Z` and numeric offsets are accepted and normalized to UTC, consistent with
  storage. Naive timestamps, date-only strings, and Unix-number timestamps fail.
- All object levels reject unknown fields. In particular, clients cannot supply
  `backend_received_at`, `site_id`, or `gateway_id`; these do not establish ownership.
  Every documented event and quality field must be present, even nullable fields.

## Two-stage HTTP boundary

`app.telemetry_validation.parse_telemetry_batch(body)` parses raw UTF-8 JSON with
decimal precision intact, validates the envelope, and then validates each event
independently. Use this entry point for wire data, rather than `request.json()` or
`TelemetryBatch.model_validate_json()`, whose float conversion can round JSON
numbers before immutable-content comparisons.

`read_telemetry_batch(request)` is the reusable FastAPI dependency. Run it after
gateway authentication in the eventual ingestion adapter. Do not bind the nested
`TelemetryBatch` directly as a FastAPI body parameter: that would reject an entire
mixed batch when just one event is invalid. `TelemetryBatch` describes fully valid
requests; the boundary deliberately retains invalid items to produce rejections.

Envelope failure raises `BatchValidationError`; the HTTP dependency maps it to
400 with `{"detail":{"reason":...,"message":...,"details":[...]}}`. Details
contain `loc`, `code`, and `message`, without echoing values or exception contexts.
The request is rejected before any event validation or persistence:

| Condition | Request reason |
| --- | --- |
| Invalid UTF-8/JSON, duplicate object keys, missing/extra fields, wrong types, or empty events | `malformed_batch` |
| Integer schema version other than 1 | `unsupported_schema_version` |
| More than 500 events | `batch_too_large` |

When multiple envelope errors exist, structural errors take precedence, then
unsupported version, then batch size. Literal JSON `NaN`/`Infinity` tokens are
invalid JSON and fail the request. A string such as `"NaN"` inside an otherwise
valid envelope fails only that item.

Successful envelope validation returns `ValidatedTelemetryBatch.items` in original
order. Each entry is either a `TelemetryEvent` awaiting ownership/persistence
processing or a `TelemetryResponseItem` with `outcome: rejected`. Structural errors
(including missing required fields) return `malformed_value`; otherwise an
unsupported metric takes precedence over an unsupported unit (`invalid_metric`,
then `invalid_unit`). Invalid items do not prevent neighboring valid items from
reaching the later ingestion service.

Every final response must retain one result per input position. Malformed identity
members are represented as null, retaining any valid identity members. Consumers
must correlate malformed items by position, not by inventing a new event identity.
All other rejections require the full identity. Rejected outcomes require an
approved item reason; accepted/duplicate outcomes require full identity and no
non-null reason. Omit the unset reason when serializing successful items, but
retain null identity fields on malformed rejections. Request-only reasons are
not permitted on response items.

This records previously unspecified boundary details: extra-field rejection,
strict JSON scalar types, duplicate JSON member rejection, deterministic error
precedence, and null identity members for malformed items. It preserves the
approved fields, clock rules, per-item behavior, and durability requirements;
it does not record pending Backend Lead or Gateway Developer acknowledgements.

## Generate and verify

From `backend/`, using the repository virtual environment:

```sh
python -m app.telemetry_openapi --output ../docs/telemetry-openapi.json
python -m unittest discover -s tests -v
```

The contract tests cover required/null values, scalar coercion, quality enums,
timestamp ownership and normalization, finite/precise numbers, batch limits,
error precedence, independent mixed items, HTTP 400 mapping, response invariants,
examples, reference resolution, and generated-document drift. They need no database.
Run the backend Ruff checks from the [development guide](../backend/README.md#development-checks).

The OpenAPI document is generated from the models using
[Pydantic JSON Schema generation](https://docs.pydantic.dev/latest/concepts/json_schema/).
The future adapter can describe its custom body parser using
[FastAPI OpenAPI configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/).
