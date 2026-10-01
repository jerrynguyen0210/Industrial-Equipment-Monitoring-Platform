# MQTT telemetry contract

## Topic and message

| Item | Rule |
| --- | --- |
| Device topic | `equipment/{device_id}/telemetry` |
| Gateway subscription | `equipment/+/telemetry` at QoS 1 |
| Device ID | One case-sensitive topic level, at most 128 characters; no `/`, `+`, or `#`. |
| Message | One UTF-8 JSON event with `schema_version: 1`; no batch wrapper. |
| Retain | Disabled. |

The event shape is shown in
[sample-event.json](../infra/mosquitto/sample-event.json). `boot_id` changes after
a device reboot, and `sequence_number` starts at zero for each boot. A retry must
keep the same identity and content.

Devices omit `gateway_received_at`, `backend_received_at`, `gateway_id`, and
`site_id`. The gateway verifies that topic and payload Device IDs match, records
its own receipt time, and wraps events in an HTTP batch.

## Credentials

Dashboard registration creates a device-specific Mosquitto account and ACL:

- Username: Device ID.
- Password: registration password.
- Permission: write only its own telemetry topic.

The provisioner still creates `device-demo-001`, the read-only
`gateway-demo-001` subscriber, and the `_health/#` account for initial setup and
tests. Anonymous connections are rejected. The gateway MQTT password is separate
from its backend bearer token.

The local listener uses plaintext TCP and binds to loopback by default. Expose it
only on a trusted lab LAN. Production requires authenticated TLS and managed
device credential rotation.

## Delivery boundaries

QoS 1 provides at-least-once delivery, so duplicates are expected. All consumers
identify an event by `(device_id, boot_id, sequence_number)`. An identical replay
is a duplicate; changed immutable content for the same identity is a conflict.

An MQTT PUBACK confirms broker receipt only. It does not confirm gateway SQLite
storage, backend acceptance, or PostgreSQL commit. Never retain telemetry because
a late subscriber could treat an old message as current.

See the [HTTP ingestion contract](telemetry-api-contract.md) for backend outcomes.
