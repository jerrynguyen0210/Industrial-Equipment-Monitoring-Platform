# Prototype temperature alert flow

Authenticated telemetry ingestion evaluates each newly accepted, valid
temperature reading in the same PostgreSQL transaction that stores it. The
existing telemetry response still reports storage outcomes; alert transitions
are visible in `alert_episodes`.

For each device, the evaluator uses `measured_at` when present with a
`synchronised` clock. Otherwise it uses `gateway_received_at`, as the current
reading and history APIs do. A reading advances alert state only when its event
time is within five minutes before to one minute after its database-generated
`backend_received_at`, and is strictly later than that device's last evaluated
event time. Older, equal-time, stale, and far-future readings remain stored
telemetry but do not advance alert state. Duplicate identities never reach the
evaluator. The freshness limits are prototype choices, not sensor specifications.

With no active alert, three consecutive evaluated readings **greater than
30°C** open one episode. A reading of 30°C or below resets the high streak.
While the episode is active, three consecutive evaluated readings **below
28°C** resolve it. A reading of 28°C or above resets the recovery streak.
Further high readings keep the existing episode active. Once resolved, a new
three-reading high streak can open another episode.

`alert_states` stores each device's event-time cursor, streaks, and active
episode ID. `alert_episodes` stores the opening and optional resolving event
times plus references to the telemetry rows that caused each transition. The
partial unique index permits at most one unresolved episode per device.
Ingestion locks device rows in device ID order, serializing concurrent alert
updates. Telemetry, state, and episode changes commit or roll back together.

After applying migration `0004_temperature_alerts`, inspect the demo result:

```sql
SELECT id, device_id, opened_at, resolved_at,
       opening_telemetry_id, resolving_telemetry_id
FROM alert_episodes
ORDER BY id;
```

This prototype flow evaluates readings as they arrive. Previously stored
telemetry is not backfilled into alert state by the migration.
