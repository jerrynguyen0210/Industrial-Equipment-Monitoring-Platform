# Temperature history API

`GET /api/v1/devices/{device_id}/telemetry/history?from=<UTC-instant>&to=<UTC-instant>`
returns one device's trustworthy temperature measurements in ascending
`measured_at` order. Equal timestamps use the telemetry row ID as a stable
tie-breaker. Both query timestamps must include a timezone. The range is
half-open (`from` included, `to` excluded) and cannot exceed seven days.

```json
{
  "device_id": "device-demo-001",
  "unit": "celsius",
  "range_start": "2026-09-26T01:00:00Z",
  "range_end": "2026-09-26T02:00:00Z",
  "truncated": false,
  "points": [
    { "measured_at": "2026-09-26T01:10:00Z", "value": "24.6", "gap_before": true },
    { "measured_at": "2026-09-26T01:10:01Z", "value": "24.7", "gap_before": false }
  ]
}
```

Only records with a non-null measurement time and `synchronised` clock quality
appear. The API never uses backend receipt time as a substitute for measurement
time. A point starts a new line segment (`gap_before: true`) when it is first in
the result, has a different boot ID, has a skipped or reversed sequence number,
or is more than two minutes after the preceding point. Two minutes is a
provisional conservative display threshold because the registry has no nominal
sampling interval. Clients plot timestamps on a time axis and must not connect
across these breaks or invent readings in empty intervals.
Values are JSON decimal strings to preserve the stored number; chart clients
parse finite values for plotting.

The response contains at most the latest 2,000 matching points in the range;
`truncated: true` means older matching points were omitted. The returned points
remain in ascending measurement-time order. An unknown device returns 404, an
invalid or oversized range returns 422, and database failures return 503.
