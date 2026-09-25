# Local MQTT telemetry topic contract

This is the prototype device-to-gateway transport on the local Mosquitto broker.
The native gateway and firmware MQTT clients are not implemented yet; the broker,
credentials, ACLs, sample event, and executable Compose check establish their
shared interface. See [the local broker runbook](../infra/README.md) for setup.

## Topic and payload

| Item | Contract |
| --- | --- |
| Publish topic | `equipment/{device_id}/telemetry`, for example `equipment/device-demo-001/telemetry` |
| Gateway subscription | `equipment/+/telemetry` at QoS 1 |
| Device ID | One nonempty, case-sensitive topic level matching the event's `device_id` and a registered device. No `/`, `+`, or `#`; use at most 128 characters. |
| Message | One UTF-8 JSON object per reading, with `schema_version: 1` and the fields in [sample-event.json](../infra/mosquitto/sample-event.json). No array or HTTP batch envelope. |
| Delivery | Device publishes at QoS 1; gateway subscribes at QoS 1. Do not set the retain flag. |

`boot_id` identifies a device boot; `sequence_number` starts at zero for that boot
and increments for each event. The pair is stable when retrying the same reading.
`measured_at` may be null when the device clock is not trustworthy; do not invent
a wall-clock measurement time. Device messages omit `gateway_received_at`,
`backend_received_at`, `gateway_id`, and `site_id`. A future gateway must verify
the authenticated topic/device mapping, check that the payload `device_id`
matches the topic, stamp `gateway_received_at` after intake, remove the MQTT-only
`schema_version` field, and wrap events in the [HTTP telemetry-batch.v1 contract](telemetry-api-contract.md).
The broker ACL limits topics, but it cannot inspect a JSON payload.

## Credentials and topic permissions

The provisioner generates local passwords and a hashed Mosquitto password file in
ignored `secrets/mosquitto/`. No working MQTT password is committed. The ACL in
[infra/mosquitto/acl](../infra/mosquitto/acl) grants:

| Username | Access |
| --- | --- |
| `device-demo-001` | Write only `equipment/device-demo-001/telemetry` |
| `gateway-demo-001` | Read `equipment/+/telemetry` |
| `health` | Read/write `_health/#` for broker health and isolated persistence checks |

Anonymous clients cannot connect. Add a unique device username/password and an
explicit write ACL rule when provisioning another device. MQTT credentials are
separate from the gateway's HTTP bearer token. The local listener has no TLS and
is published only to loopback by default; use it only on a trusted development
host or controlled lab network. A deployed broker needs authenticated TLS and
device-specific provisioning.

## QoS 1, duplicates, and retained messages

QoS 1 means **at least once** on each MQTT hop. A reconnect or lost acknowledgement
can deliver the same reading again. Consumers must key an event by
`(device_id, boot_id, sequence_number)`, preserve the original reading on matching
replay, and report changed immutable content as a conflict. This agrees with the
[backend identity contract](telemetry-api-contract.md#persistence-retries-and-failure-boundary).
A publisher's MQTT PUBACK confirms broker receipt; it does not confirm gateway
SQLite commit, HTTP acceptance, or database durability. Those are separate
boundaries for the future gateway implementation.

Telemetry is an event stream: **never retain** messages on
`equipment/{device_id}/telemetry`. A late subscriber must not mistake an old
reading for a new reading. The broker leaves retain support enabled for isolated
`_health/` persistence checks, so the no-retain telemetry rule is a client
contract, not a broker-enforced flag. If a prototype client previously retained
telemetry, clear that topic by publishing a zero-byte message with retain set
using its authorized device account, then resume non-retained publishing.

The [Mosquitto MQTT reference](https://mosquitto.org/man/mqtt-7.html) defines QoS 1
and retained-message behavior. The [Mosquitto ACL reference](https://mosquitto.org/man/mosquitto-conf-5.html)
documents the topic access rules used here.
