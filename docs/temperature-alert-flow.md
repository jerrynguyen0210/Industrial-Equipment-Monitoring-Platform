# Prototype temperature alert flow

The backend evaluates each newly accepted valid temperature in the same
transaction that stores it.

## Ordering and freshness

The evaluator uses synchronised `measured_at`; otherwise it uses
`gateway_received_at`. A reading advances state only when it:

- Is later than the device's last evaluated event.
- Is no more than five minutes old at backend receipt.
- Is no more than one minute in the future at backend receipt.

Older, equal-time, stale, future, and duplicate events remain stored but do not
change alerts.

## State changes

1. Three consecutive evaluated readings above 30°C open one episode.
2. A reading at or below 30°C resets the opening streak.
3. While active, three consecutive readings below 28°C resolve the episode.
4. A reading at or above 28°C resets the recovery streak.

`alert_states` stores the event cursor, streaks, and active episode. An
`alert_episodes` row records the telemetry that opened and resolved it. Row locks
serialize concurrent changes, and telemetry, state, and episode changes commit
or roll back together.

Inspect episodes after applying migration `0004_temperature_alerts`:

```sql
SELECT id, device_id, opened_at, resolved_at,
       opening_telemetry_id, resolving_telemetry_id
FROM alert_episodes
ORDER BY id;
```

The migration does not backfill old telemetry. Thresholds and freshness windows
are prototype constants, and the dashboard sample alert card does not display
these episodes.
