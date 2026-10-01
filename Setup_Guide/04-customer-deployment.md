# 4. Prepare a customer release

The current system is suitable for a supervised evaluation with synthetic data
on a trusted network. It is not ready for unattended production use, equipment
control, or safety alarms.

## 1. Close the release gates

Assign an owner and retain evidence for each gate:

| Area | Required evidence |
| --- | --- |
| Transport | MQTT TLS on device, gateway, and broker; certificate validation, expiry, rotation, and reconnect tests. |
| User access | Dashboard login, roles, tenant/site authorization, and access tests. |
| API edge | HTTPS, restricted direct backend access, managed secret rotation, and revocation tests. |
| Provisioning | Unique customer identities, replacement/revocation, and an auditable inventory. |
| Recovery | Encrypted off-host backups, isolated restore tests, retention, capacity alerts, and recovery objectives. |
| Fleet and alerts | Device health, queue limits, approved thresholds, notification ownership, and upgrade/rollback procedures. |
| Delivery | Versioned artifacts, supported topology, license, lifecycle, and site/security review. |

## 2. Complete the site record

Record the customer/site owner, contacts, data classification, retention,
hardware inventory, network diagram, IDs, secret-store references, certificate
owners, software versions, backup location, recovery objectives, alert policy,
maintenance window, and rollback owner. Never put secret values in the record.

## 3. Deploy after the gates pass

1. Agree on equipment scope, probe placement, sampling interval, data ownership,
   downtime, alarms, network, backup, and support.
2. Build immutable artifacts from a reviewed commit in an isolated staging
   environment.
3. Provision unique customer site, gateway, device, database, and credentials.
   Do not run the demo seed in a customer database.
4. Apply migrations, register assets, and verify the exact ownership chain.
5. Install the probe, customer firmware, gateway service, TLS, and firewall rules.
6. Verify physical reading, MQTT receipt, SQLite storage, backend acceptance,
   dashboard history, probe failure, network outage, recovery, and duplicates.
7. Restore a backup in isolation, test rollback and credential revocation, and
   demonstrate monitoring and escalation.
8. Hand over inventory, diagrams, access, recovery evidence, known limits,
   update cadence, and support ownership. Obtain recorded acceptance.

The local Compose topology is a staging reference. Production architecture and
operations must be reviewed and tested for the customer environment.
