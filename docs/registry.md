# Equipment registry

The PostgreSQL registry defines the ownership chain:

```text
site -> gateway -> device -> telemetry and alert history
```

## Schema

| Table | Primary key | Required relationship and fields |
| --- | --- | --- |
| `sites` | `site_id` | `name`, `enabled` |
| `gateways` | `gateway_id` | `site_id`, `name`, `enabled` |
| `devices` | `device_id` | `gateway_id`, `name`, `enabled`; optional password hash and last contact; managed-MQTT flag |

IDs are case-sensitive strings up to 128 characters. A Device ID is globally
unique. Foreign keys use `ON DELETE RESTRICT`, so parents and devices with
history cannot be deleted accidentally. Disable an entity when history must be
preserved.

## Ownership decisions

For an authenticated gateway and a device, the backend returns one internal
decision:

| Result | Meaning |
| --- | --- |
| `allowed` | Device belongs to the gateway and site, gateway, and device are enabled. |
| `unknown_device` | Device is not registered. |
| `wrong_gateway` | Device belongs to another gateway. |
| `disabled` | Ownership matches but an entity is disabled. |

Authentication supplies the gateway identity; payload IDs cannot authenticate a
caller. Ingestion holds shared registry row locks until commit so a concurrent
ownership change cannot authorize a stale write.

## Apply migrations and seed demo data

1. Start the database and backend.
2. Apply the current schema:

   ```sh
   docker compose exec -T backend python -m alembic upgrade head
   docker compose exec -T backend python -m alembic current
   ```

3. For a lab only, insert the demo hierarchy:

   ```sh
   docker compose exec -T backend python -m app.db.seed
   ```

The seed creates `site-demo-001 -> gateway-demo-001 -> device-demo-001`. It is
repeatable, preserves existing names and enabled states, and rolls back on an
ownership conflict. Do not run it in a customer database.

Key revisions are `0001_registry`, `0002_telemetry`,
`0004_temperature_alerts`, `0005_device_presence`, and
`0006_mqtt_management`. The last revision records whether device deletion should
revoke a broker account created by the API. Migrations are explicit; API startup
does not create tables or seed rows.

## Recovery

A downgrade can delete registry, telemetry, or alerts. Before any downgrade:

1. Stop writers.
2. Create a PostgreSQL backup.
3. Run the downgrade only on a disposable or isolated database first.
4. Inspect `alembic current` before retrying a failed operation.

`upgrade head` recreates schema only; it cannot restore deleted data. Restore a
backup into an isolated database and validate it before switching consumers.

Run the PostgreSQL suites described in
[backend/README.md](../backend/README.md#run-the-checks) to verify constraints,
concurrency, migrations, seeding, and ownership.
