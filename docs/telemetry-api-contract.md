# Telemetry API ingestion contract

The backend implements authenticated ingestion, request/response models and validation
for `telemetry-batch.v1`, following sections 3, 5, and 7 of the
[approved contract](Technical_Lead_Telemetry_Ingestion_Contract_Approval_Sprint01.pdf).
The [OpenAPI 3.1 document](telemetry-openapi.json) describes the implemented
`POST /api/v1/telemetry/batches` operation, bearer authentication requirement,
schemas, valid/null-time/mixed request examples, mixed outcomes, and HTTP 400 errors.

The running `/openapi.json` includes this same operation alongside health routes.
`app.telemetry_api` owns HTTP mapping; `app.gateway_auth` resolves credentials;
`app.ingestion` owns authorization, classification and transaction coordination.
Validation alone never returns `accepted` or `duplicate`.

## Prototype credentials and authorization

Set `GATEWAY_CREDENTIALS_JSON` to a JSON object mapping registered gateway IDs to
unique bearer tokens. Generate tokens locally (for example, `secrets.token_urlsafe(32)`);
send the corresponding token as `Authorization: Bearer <token>`. Multiple mappings
support dedicated simulator gateways. Tokens are runtime secrets, never public
frontend settings. Missing/empty configuration disables access, not health checks.
Invalid JSON, duplicate IDs/tokens, invalid token syntax, and placeholder tokens
fail startup without echoing values. Changes require restarting the backend.

Missing, malformed, repeated or incorrect Authorization headers return 401 with
`detail.reason: invalid_gateway_credential` and `WWW-Authenticate: Bearer`, before
body parsing or database access. `X-Gateway-ID` does not grant or change identity.
A token for an unregistered or disabled gateway, or a gateway under a disabled site,
returns 403 `gateway_not_authorized` before processing items in a valid envelope.
Payload `gateway_id`/`site_id`/`backend_received_at` fields are forbidden.

Unknown devices return `rejected/unknown_device`; a device assigned to another
gateway returns `rejected/wrong_gateway`. For this prototype, disabling a device
revokes its gateway's ingestion eligibility and also returns `wrong_gateway`.
This records the previously unspecified disabled-device mapping without adding a
new item reason. Validation failures take precedence over ownership failures.
The database transaction takes shared row locks on the authenticated gateway/site
and existing device assignments until commit, so concurrent registry changes
cannot authorize an insert using stale ownership. Shared locks permit concurrent
ingestion. The separate read-only registry helper does not acquire these locks.

This prototype uses an explicit runtime credential map. It has no credential
management endpoints, expiry mechanism or production identity-provider integration.
Use HTTPS for any deployed credential-bearing connection.

## Persistence, retries and failure boundary

All processable items share one transaction; permanent item rejections leave valid
neighbors eligible for commit. PostgreSQL `ON CONFLICT DO NOTHING` against
`uq_telemetry_identity` arbitrates concurrent identities. Existing rows are compared
on `schema_version`, event identity, `measured_at`, `device_uptime_ms`, `metric`,
`value`, `unit`, and `quality`. Receipt times and HTTP/batch metadata are excluded,
as required by section 4.1 of the approval. Matching retries return `duplicate`;
different immutable content returns `rejected/identity_conflict` and logs a safe
conflict event. Neither case updates the original row or either receipt timestamp.

New inserts omit `backend_received_at`, letting PostgreSQL `clock_timestamp()`
assign UTC processing receipt time. Savepoints turn individual PostgreSQL data
representation errors (for example, a finite number beyond PostgreSQL NUMERIC
capacity) into `malformed_value` without rolling back valid peers. No arbitrary
sensor range or temperature rounding is added.

The service returns results only after its transaction commits. Database, pool,
lock or commit errors return 503 `ingestion_unavailable` with a server-generated
`batch_id`, no item results and no credential/payload details. A commit failure
rolls back the transaction when possible. If the commit outcome is uncertain,
retry the unchanged batch: already committed rows become duplicates. HTTP 200
contains one ordered result per input, even when every item was rejected.

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
- IDs are nonempty, case-sensitive strings of at most 128 characters, without NUL, preserved
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
gateway credential authentication in the ingestion adapter. Do not bind the nested
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
The PostgreSQL ingestion suite in `backend/tests/integration/test_ingestion.py`
verifies the real route, durable storage, concurrent retry/conflict classification,
ownership locks and commit failures. The [shared smoke suite](../tests/README.md)
invokes the API-mode simulator against the packaged backend over HTTP and checks
telemetry persistence across a full stack restart.

The OpenAPI document is generated from the models using
[Pydantic JSON Schema generation](https://docs.pydantic.dev/latest/concepts/json_schema/).
The adapter describes its custom body parser using
[FastAPI OpenAPI configuration](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/).
