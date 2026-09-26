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
        "value": 23.75,
        "unit": "celsius",
        "measured_at": "2026-09-26T02:30:00Z",
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

The endpoint reads registry and telemetry data from PostgreSQL. It orders each
device's readings by backend receipt time, with the telemetry row ID as a
deterministic tie-breaker. `measured_at` remains the device's measurement time;
it is nullable and must not be replaced by backend receipt time. Clients can
show measurement age only when that timestamp exists and `clock_quality` is
`synchronised`. A missing `latest_reading` means no valid reading is recorded;
it is not a zero or a healthy status.

Database failures return HTTP 503 with a machine-readable
`device_status_unavailable` reason. The endpoint returns all registered devices,
including disabled registrations; the registry's `enabled` flag is not a device
connectivity signal. This API does not provide online state or active alert
counts because neither is currently modeled by the platform.
