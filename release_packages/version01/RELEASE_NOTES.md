# Industrial Equipment Monitoring Platform — version01

Release type: **controlled customer evaluation**  
Source commit: `98461f28eca76bed4da7f85598a6aac3643d2ac0`  
Packaged: `2026-09-30T00:15:40Z`

## Purpose

`version01` is a self-contained source release for a supervised customer-side
functional test on a trusted, isolated network using synthetic or dedicated
test equipment. Start with [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

The package contains the Docker Compose platform, database migrations, simulator,
native Linux gateway source, ESP32 firmware source, automated Linux setup tools,
tests, and technical documentation. Docker images are built on the target host;
the first installation therefore requires internet access to obtain the pinned
base images and application dependencies.

## Included capabilities

- PostgreSQL-backed equipment registry, telemetry history, and prototype
  temperature alert episodes.
- FastAPI health, readiness, device, telemetry, history, and alert APIs.
- React dashboard served through nginx with `/api` proxying.
- Authenticated local Mosquitto accounts and topic ACLs.
- Deterministic synthetic telemetry for repeatable acceptance testing.
- Native gateway with a durable SQLite queue and HTTP retry behavior.
- ESP32 firmware for a DS18B20 probe or explicitly selected demo input.

## Known limitations

This is not a production release. In particular:

- The dashboard and read APIs have no user authentication or authorization.
- Device/gateway MQTT uses plaintext TCP and has no TLS.
- Provisioning uses fixed demo identities intended only for evaluation.
- Published service ports bind to loopback by default.
- Backup, restore, telemetry retention, and fleet upgrade processes are not
  automated.
- Temperature thresholds are fixed prototype values; the dashboard alert card
  is sample data and is not a live safety alarm.
- No project `LICENSE` file is included. Distribution and use must remain within
  the customer's separately approved evaluation terms.

Do not expose this release directly to the public internet, ingest production or
sensitive customer data, use it to control equipment, or treat it as a safety
system. The complete production release gates are in
[Setup_Guide/04-customer-deployment.md](Setup_Guide/04-customer-deployment.md).

## Package integrity

`SHA256SUMS` covers every regular file in the extracted `version01` directory
except the manifest itself. The sibling archive checksum verifies the compressed
delivery artifact before extraction.
