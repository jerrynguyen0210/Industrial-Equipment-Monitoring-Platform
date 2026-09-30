# Health API contract

The backend exposes unauthenticated, read-only health checks for local integration
at `http://localhost:8000` by default. Every response below uses
`Content-Type: application/json`. `GET /openapi.json` publishes the response
schemas, including readiness HTTP 503.

## Endpoints and responses

| Endpoint | Condition | HTTP status | JSON body |
| --- | --- | --- | --- |
| `GET /health` | API can serve requests | 200 | `{"status":"ok"}` |
| `GET /ready` | Database connection, authentication, and `SELECT 1` succeed | 200 | `{"status":"ready","database":"ok"}` |
| `GET /ready` | Database connection, authentication, or query fails | 503 | `{"status":"unavailable","database":"unavailable"}` |

`status` is always a required string. Readiness also requires the string field
`database`; liveness omits it. Responses contain no credentials, connection
strings, hostnames, or raw exception messages.

`GET /api/health/live` and `GET /api/health/ready` remain supported aliases with
the same status codes and bodies. The frontend proxy uses `/api/health/ready`;
call `/health` and `/ready` directly on the backend port. This is an additive
route change: existing clients retain their response bodies and paths.

## Dependency and recovery behavior

Liveness performs no database work. Readiness opens a new authenticated PostgreSQL
connection and executes `SELECT 1` on every request. Connection attempts use a
three-second connection timeout and queries use a two-second statement timeout.
These are separate driver/database limits, not a single HTTP request deadline.
Connections close after each probe, including query failures.

A database failure returns HTTP 503 and the structured unavailable body. A later
successful probe returns HTTP 200 without restarting the API. During a database
outage, `/health` continues to return HTTP 200. Compose uses `/ready` for the
backend container health check.

Missing or invalid database configuration fails application startup; it is not
treated as a running but unready service. See the [configuration guide](configuration.md)
for `DATABASE_URL` and `PG*` precedence and the [backend setup](../backend/README.md)
for startup commands. Readiness verifies connectivity and query execution only;
it does not certify migrations, ingestion, equipment state, or other services.

## Machine checks

With the backend running, use `curl` (`curl.exe` in Windows PowerShell):

```sh
curl --fail-with-body --silent --show-error http://localhost:8000/health
curl --fail-with-body --silent --show-error http://localhost:8000/ready
```

HTTP 503 produces a nonzero curl exit code while retaining the JSON failure body.
Automation can check both the HTTP status and the fields above.

Backend tests cover success, dependency failure, recovery, aliases, secret-safe
responses/logs, and the OpenAPI response declarations. The
[Compose smoke suite](../tests/README.md) checks the real database outage and
recovery behavior through both the backend and frontend proxy.
