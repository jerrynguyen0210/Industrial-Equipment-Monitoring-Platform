# 4. Prepare a customer release

**Release status: not ready for an unattended production customer deployment.**
The lab instructions can demonstrate the data path, but copying `compose.yaml`
and demo credentials to a customer site would expose data and leave operations
unsupported. A controlled evaluation can use the lab guide only with synthetic
data, a trusted isolated network, an explicit evaluation scope, and a person
watching the gateway and database. Do not present prototype alerts as a safety
alarm or use this system to control equipment.

## Release gates

Complete and verify these before using real customer data or offering a
production service. Assign an owner and keep test evidence for each gate.

| Gate | Current state | Required release evidence |
| --- | --- | --- |
| Device and gateway transport | ESP32 and gateway MQTT use plaintext TCP; broker listens without TLS. | Implement authenticated MQTT over TLS on both clients and broker; test certificate validation, expiry, rotation, and reconnect on target hardware. |
| Dashboard and read API access | No user accounts or authorization; device/history endpoints are readable by anyone who can reach them. | Implement customer identity, roles, tenant/site authorization, session handling, and access tests. |
| HTTP/API edge | Local stack publishes plaintext HTTP and uses a prototype static gateway bearer map. | Put the UI/API behind HTTPS, restrict direct backend access, use managed secret distribution/rotation, and test revoked credentials. Gateway HTTPS certificate checking already exists but needs deployment verification. |
| Device provisioning | Broker provisioner and ACL contain only three fixed demo accounts. Registry seed creates fixed demo IDs. | Implement repeatable unique per-customer/site/gateway/device provisioning, revocation, replacement, and an auditable inventory. |
| Data recovery | Named volumes and a gateway SQLite queue persist locally; no automated off-host backup, restore drill, or retention policy. | Schedule encrypted backups, restore into an isolated environment, set retention/capacity thresholds, and prove recovery objectives. |
| Fleet and alert operations | ESP32 has a bounded RAM queue; gateway has no capacity limit. Backend alert thresholds are fixed at 30°C/28°C, while the dashboard alert card uses unrelated sample data. | Establish capacity/loss behavior, device health and clock monitoring, site-approved thresholds, alert delivery/acknowledgement if promised, support diagnostics, and field upgrade/rollback procedure. |
| Product delivery | Compose is documented as a development stack; no packaged production topology or license file. | Version and test deployment artifacts, define support lifecycle, supply a license, and complete site/security review. |

This table is a release checklist, not a claim that configuration alone closes
the gaps. In particular, a reverse proxy does not add MQTT TLS to the existing
ESP32 or gateway client, and a firewall does not add dashboard user authorization.

## Site worksheet

Create one completed copy per customer and keep secrets in the customer's
approved secret store, never in this document or Git.

| Item | Record |
| --- | --- |
| Customer, site, equipment owner, support contacts |  |
| Data classification, retention, location, and access requirements |  |
| Installation date, maintenance window, rollback owner |  |
| Server/Pi model, OS, storage, power, network diagram |  |
| ESP32 board revision, probe model, serial number, mounting and cable route |  |
| Site ID, gateway ID, device IDs, credential inventory references |  |
| Broker/API/UI DNS names, ports, TLS certificate owner and expiry |  |
| Wi-Fi coverage and firewall rules approved by customer IT |  |
| Version: Git commit, container image digests, gateway binary, ESP-IDF build |  |
| Backup location, retention, restore test date, recovery objectives |  |
| Alert thresholds, notification path, escalation, and response owner |  |

## Deployment sequence after the gates pass

1. **Design the site.** Agree on equipment scope, temperature range and probe
   placement, allowable downtime, sampling interval, data ownership, and whether
   alarms are informational or operational. Confirm power, network, access,
   certificate, backup, and support requirements with the customer.
2. **Stage an isolated environment.** Build immutable release artifacts from a
   reviewed commit. Provision distinct customer database, broker, gateway and
   device identities. Use no demo seed, synthetic firmware mode, sample token,
   or committed default database password. Protect secrets and firmware images.
3. **Apply schema and register assets.** Apply the release's Alembic migration
   to the staged database. Register site → gateway → device IDs, then verify
   exact ownership and enabled states. The current repository has no registry
   management UI/API; the release needs a supported provisioning workflow.
4. **Install the edge.** Mount and wire the probe, flash a customer-specific
   firmware image, record its identity and version, configure the gateway's
   durable storage and service, and connect through authenticated TLS. Keep the
   broker and backend reachable under the agreed firewall rules.
5. **Verify end to end.** Observe physical readings at the probe, MQTT receipt,
   gateway `message_stored` and `batch_applied`, backend rows, and dashboard
   history. Compare against a trusted thermometer and record acceptable error.
   Disconnect the probe and network separately; verify fault reporting, queue
   behavior, recovery, duplicate handling, and no misleading live value.
6. **Test operations.** Restore a backup in isolation, verify a deployment
   rollback, expire/revoke a test credential, test disk pressure and monitoring,
   and demonstrate the support contact and incident escalation path.
7. **Handover.** Give the customer the site inventory, architecture/network
   diagram, operator access, backup/restore record, acceptance evidence, known
   limits, update cadence, and support ownership. Obtain acceptance against the
   agreed criteria before switching to normal operations.

Do not use the local `python -m app.seed` in a real customer database: it creates
demo IDs. The current Compose setup is a useful staging reference, but the final
production topology, security controls, and release process must be implemented
and tested before this sequence can be executed as a customer runbook.
