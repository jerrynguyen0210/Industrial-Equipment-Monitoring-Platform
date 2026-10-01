# Temperature history API

Request a bounded UTC range:

```text
GET /api/v1/devices/{device_id}/telemetry?from=<instant>&to=<instant>
```

`/telemetry/history` remains an alias. Both timestamps require a timezone. The
range includes `from`, excludes `to`, and may span at most seven days.

The response contains at most the latest 2,000 matching points, returned in
ascending event time. `truncated: true` means older matches were omitted.

```json
{
  "device_id": "esp-nano",
  "unit": "celsius",
  "range_start": "2026-10-01T01:00:00Z",
  "range_end": "2026-10-01T02:00:00Z",
  "truncated": false,
  "points": [
    {
      "event_at": "2026-10-01T01:10:00Z",
      "timestamp_source": "measured_at",
      "measured_at": "2026-10-01T01:10:00Z",
      "gateway_received_at": "2026-10-01T01:10:01Z",
      "clock_quality": "synchronised",
      "value": "24.6",
      "unit": "celsius",
      "gap_before": true
    }
  ]
}
```

Event time uses a synchronised `measured_at`; all other points use
`gateway_received_at`. Backend receipt time never orders history. Equal event
times use the telemetry row ID as a stable tie-breaker. Values are decimal
strings and timestamps are UTC.

`gap_before: true` starts a new chart segment when the point is first, changes
boot or timestamp source, skips/reverses sequence, or follows a gap longer than
two minutes. Clients must not draw across these gaps or invent missing values.

Unknown devices return 404, invalid ranges return 422, and database failures
return 503.
