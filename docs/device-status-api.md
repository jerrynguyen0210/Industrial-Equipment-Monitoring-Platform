# Device status API

`GET /api/v1/devices` returns registered devices in name and ID order, with the
latest stored temperature reading and connection status for each device:

```json
{
  "devices": [
    {
      "device_id": "device-demo-001",
      "name": "Demo device",
      "gateway_id": "gateway-demo-001",
      "enabled": true,
      "online": false,
      "last_seen_at": null,
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
      "gateway_id": "gateway-demo-001",
      "enabled": true,
      "online": false,
      "last_seen_at": null,
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
including disabled registrations. `online` is true only for an enabled device on
an enabled gateway and site when the server accepted a telemetry reading or a
valid heartbeat in the previous 90 seconds. `last_seen_at` is the server time of
that contact, stored in PostgreSQL and retained across API restarts. Offline
means no recent confirmed server contact; it does not diagnose the cause.
In particular, a connected MQTT socket with no readings or heartbeat still
appears offline in this API.

## Device management

`GET /api/v1/gateways` lists enabled gateways for the registration form.
`POST /api/v1/devices` accepts `device_id`, `gateway_id`, `name`, and `password`.
Device IDs may contain letters, digits, `_`, and `-`; passwords must be 12–128
characters. The password is stored as a salted PBKDF2 hash and is never returned.
Registration also creates a Mosquitto account with the Device ID as MQTT
username and the same password, scoped to `equipment/<Device ID>/telemetry`.
If a broker password-file account already has that ID, registration verifies
that the supplied password connects and keeps the existing account.
The new device starts offline. Broker failure returns 503 and rolls back the
database registration. Duplicate database IDs or conflicting MQTT credentials
return 409; unavailable gateways return 404, and invalid input returns 422.
The management API follows
the existing local dashboard's access model, which has no operator login; deploy
it only behind trusted access controls.

`POST /api/v1/devices/{device_id}/mqtt` accepts the existing registration
password and creates or updates its managed MQTT account, or verifies a
matching older password-file account. Use it for devices
registered before automatic broker provisioning. A wrong password returns 401.

`DELETE /api/v1/devices/{device_id}` removes a registration that has no saved
telemetry or alerts. It returns 204 after deletion, 404 when the device is not
registered, and 409 with `device_has_history` when retained readings or alert
records still reference it. The 409 response leaves the registration and its
history unchanged. The dashboard asks for confirmation before deletion and
refreshes the list afterward. Accounts created through registration are revoked
from Mosquitto when the device is removed. Older manually provisioned broker
accounts are not altered by database deletion.

`POST /api/v1/devices/{device_id}/heartbeat` accepts
`{"password":"the-registration-password"}` and returns 204 when authenticated.
Send a heartbeat at least every 60 seconds to keep status online. A device that
publishes valid telemetry through the existing MQTT gateway also becomes online
when the backend accepts readings received by the gateway within the last 90
seconds; queued older readings do not update presence. The ESP32 firmware can
send a heartbeat every 30 seconds when its backend host is configured, even
with the temperature source disabled. Use the same Device ID and password in
the ESP32 firmware for MQTT and heartbeats. An existing registration's password
cannot be read back; removing and registering a device again is possible only
when it has no saved readings or alerts. The dashboard
polls status every 15 seconds, so an offline transition can appear up to 15
seconds after the 90-second server contact window ends.
