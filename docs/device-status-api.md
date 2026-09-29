# Device status API

`GET /api/v1/devices` returns registered devices in name and ID order, with the
latest stored temperature reading for each device:

```json
{
  "devices": [
    {
      "device_id": "device-demo-001",
      "name": "Demo device",
      "latest_reading": {
        "value": "23.75",
        "unit": "celsius",
        "measured_at": "2026-09-26T02:30:00Z",
        "gateway_received_at": "2026-09-26T02:30:01Z",
        "event_at": "2026-09-26T02:30:00Z",
        "timestamp_source": "measured_at",
        "clock_quality": "synchronised"
      }
    },
    {
      "device_id": "device-without-data",
      "name": "New device",
      "latest_reading": null
    }
  ]
}
```

The endpoint reads registry and telemetry data from PostgreSQL. It chooses the
highest `event_at` per device, with the telemetry row ID as a deterministic
tie-breaker. `event_at` is `measured_at` only when it is present and clock quality
is `synchronised`; otherwise it is `gateway_received_at`. `timestamp_source`
identifies which time was used. `measured_at` remains the original nullable device
time even when it is untrustworthy. Neither event time nor current selection uses
backend receipt time, so a delayed replay of an older event does not displace a
newer reading. A missing `latest_reading` means no valid reading is recorded;
it is not a zero or a healthy status. Values are JSON decimal strings to
preserve the stored numeric representation; clients must validate them before
display or plotting.

Database failures return HTTP 503 with a machine-readable
`device_status_unavailable` reason. The endpoint returns all registered devices,
including disabled registrations; the registry's `enabled` flag is not a device
connectivity signal. This API does not provide online state or active alert
counts because neither is currently modeled by the platform.
