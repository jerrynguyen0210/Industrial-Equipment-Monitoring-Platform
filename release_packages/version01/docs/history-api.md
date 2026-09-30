# Temperature history API

`GET /api/v1/devices/{device_id}/telemetry?from=<UTC-instant>&to=<UTC-instant>`
returns one device's temperature readings in ascending `event_at` order. The
previous `/telemetry/history` URL remains an alias. Equal event times use the
telemetry row ID as a stable tie-breaker. Both query timestamps must include a
timezone. The range is half-open (`from` included, `to` excluded) and cannot
exceed seven days.

```json
{
  "device_id": "device-demo-001",
  "unit": "celsius",
  "range_start": "2026-09-26T01:00:00Z",
  "range_end": "2026-09-26T02:00:00Z",
  "truncated": false,
  "points": [
    {
      "event_at": "2026-09-26T01:10:00Z",
      "timestamp_source": "measured_at",
      "measured_at": "2026-09-26T01:10:00Z",
      "gateway_received_at": "2026-09-26T01:10:01Z",
      "clock_quality": "synchronised",
      "value": "24.6",
      "unit": "celsius",
      "gap_before": true
    },
    {
      "event_at": "2026-09-26T01:11:00Z",
      "timestamp_source": "gateway_received_at",
      "measured_at": null,
      "gateway_received_at": "2026-09-26T01:11:00Z",
      "clock_quality": "unknown",
      "value": "24.7",
      "unit": "celsius",
      "gap_before": true
    }
  ]
}
```

`event_at` uses `measured_at` only when it is present and clock quality is
`synchronised`. Otherwise it uses `gateway_received_at`, while preserving the
original nullable `measured_at`. The `timestamp_source` and `clock_quality` fields
let clients label the time accurately. Backend receipt time is never used to
order history. All returned timestamp strings include a timezone, normalized to
UTC. Values are JSON decimal strings to preserve the stored number.

A point starts a new line segment (`gap_before: true`) when it is first in the
result, has a different boot ID, has a skipped or reversed sequence number,
changes timestamp source, or is more than two minutes after the preceding point.
Two minutes is a provisional display threshold because the registry has no
nominal sampling interval. Clients must not connect across these breaks or invent
readings in empty intervals.

The response contains at most the latest 2,000 matching points in the range;
`truncated: true` means older matching points were omitted. Returned points
remain in ascending event-time order. An unknown device returns 404, an invalid
or oversized range returns 422, and database failures return 503.
