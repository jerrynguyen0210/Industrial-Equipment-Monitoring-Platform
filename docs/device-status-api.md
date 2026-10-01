# Device management and status API

## List devices

`GET /api/v1/devices` returns every registered device in name and ID order:

```json
{
  "devices": [
    {
      "device_id": "esp-nano",
      "name": "Workshop sensor",
      "gateway_id": "gateway-demo-001",
      "enabled": true,
      "online": true,
      "last_seen_at": "2026-10-01T01:20:00Z",
      "latest_reading": {
        "value": "23.75",
        "unit": "celsius",
        "event_at": "2026-10-01T01:19:58Z",
        "timestamp_source": "measured_at",
        "measured_at": "2026-10-01T01:19:58Z",
        "gateway_received_at": "2026-10-01T01:19:59Z",
        "clock_quality": "synchronised"
      }
    }
  ]
}
```

`online` is true only when the device, gateway, and site are enabled and the
server accepted a heartbeat or current telemetry within 90 seconds. Offline
means the server has not confirmed recent contact; it does not identify whether
power, Wi-Fi, MQTT, the gateway, or the sensor failed. The dashboard polls every
15 seconds.

The latest reading uses `measured_at` only with a synchronised clock; otherwise
it uses `gateway_received_at`. A delayed older event cannot replace a newer one.
Values are decimal strings. `latest_reading: null` means no reading is stored.
Database failure returns HTTP 503 with `device_status_unavailable`.

## Register a device

1. Get enabled gateway choices with `GET /api/v1/gateways`.
2. Send `POST /api/v1/devices` with `device_id`, `gateway_id`, `name`, and
   `password`.
3. Configure the ESP32 with that exact Device ID and password.

Device IDs allow letters, digits, `_`, and `-`. Passwords are 12–128 characters.
The backend stores a salted PBKDF2 hash and never returns the password.

Registration also creates a Mosquitto account. The Device ID is the MQTT username,
the registration password is the MQTT password, and the ACL allows publishing
only to `equipment/<device_id>/telemetry`. Database registration and broker
provisioning succeed or fail together. No manual `add_device.py` step is needed.

| Result | HTTP status |
| --- | --- |
| Created | 201 |
| Invalid input | 422 |
| Unknown or disabled gateway | 404 |
| Duplicate ID or conflicting broker account | 409 |
| Broker update failed | 503 |

For a registration created before automatic provisioning, send its password to
`POST /api/v1/devices/{device_id}/mqtt`. A wrong password returns 401.

## Report presence

`POST /api/v1/devices/{device_id}/heartbeat` accepts
`{"password":"<registration-password>"}` and returns 204. Firmware sends a
heartbeat every 30 seconds when its backend host is configured. Accepted recent
telemetry also refreshes presence; delayed queued readings do not.

## Remove a device

`DELETE /api/v1/devices/{device_id}` returns 204 and revokes a broker account
created by registration. It returns 409 `device_has_history` when telemetry or
alerts still reference the device, leaving all data unchanged. Unknown devices
return 404. Older manually provisioned broker accounts are not removed.

The local management API has no operator login. Restrict it to trusted lab access.
