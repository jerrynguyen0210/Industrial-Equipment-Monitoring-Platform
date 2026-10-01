# Health API

The backend exposes unauthenticated JSON health checks on port 8000.

| Endpoint | Meaning | Success | Failure |
| --- | --- | --- | --- |
| `GET /health` | API process can serve requests. | 200 `{"status":"ok"}` | Process unavailable. |
| `GET /ready` | A new PostgreSQL connection and `SELECT 1` succeed. | 200 `{"status":"ready","database":"ok"}` | 503 `{"status":"unavailable","database":"unavailable"}` |

`/api/health/live` and `/api/health/ready` are equivalent aliases. The frontend
uses the readiness alias through its `/api` proxy.

Readiness opens a connection for every request with a three-second connection
timeout and two-second statement timeout. A recovered database becomes ready
without an API restart. Liveness performs no database work and remains healthy
during a database outage.

Readiness confirms connectivity only. It does not check migration currency,
telemetry ingestion, MQTT, or equipment state. Invalid database configuration
prevents backend startup.

Verify a running backend:

```sh
curl --fail-with-body --silent --show-error http://localhost:8000/health
curl --fail-with-body --silent --show-error http://localhost:8000/ready
```

Responses and logs omit credentials, connection strings, hostnames, and raw
exceptions. Schemas, including readiness 503, are published in `/openapi.json`.
