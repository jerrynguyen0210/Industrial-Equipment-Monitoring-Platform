# Setup and deployment guide

Follow these documents in order. Commands use Bash on Linux unless a step says
otherwise. Run repository commands from the repository root; run `idf.py` from
`firmware/`.

For a new 64-bit Raspberry Pi OS, Debian, or Ubuntu host, the automated lab
installer performs step 1 (including Docker installation, credential
provisioning, startup, migration, seeding, and health checks):

```sh
./Setup_Guide/install.sh
```

Run it as your normal user. It preserves existing configuration, credentials,
volumes, and registry data when rerun. See
[the lab installation procedure](01-lab-installation.md#automated-installation)
for supported hosts and options.

After connecting an ESP32 by USB, install the pinned compiler, configure the
firmware on first use, build it, and flash the board with:

```sh
./agents/hardware_script/compile-and-flash-esp32.sh --monitor
```

See [the hardware and gateway guide](02-hardware-and-gateway.md#automated-firmware-build-and-flash)
for serial-port, configuration, and Linux permission details.

| Step | Document | Outcome |
| --- | --- | --- |
| 1 | [Install and run the lab system](01-lab-installation.md) | Four Compose services, migrated database, and a working dashboard. |
| 2 | [Connect the gateway and ESP32](02-hardware-and-gateway.md) | Physical temperature readings travel through MQTT, SQLite, and the API. |
| 3 | [Operate and recover the system](03-operations.md) | Health, logs, backups, restart, and fault checks. |
| 4 | [Prepare a customer release](04-customer-deployment.md) | Release gates, site preparation, acceptance, and handover. |

## What this release can do

The local stack runs PostgreSQL, Mosquitto, a FastAPI backend, and a React
dashboard. A native Linux gateway subscribes to MQTT, queues readings in SQLite,
and forwards batches to the backend. ESP32 firmware reads one externally powered
DS18B20 probe and publishes readings. The dashboard shows stored readings and
history. The backend records prototype temperature alert episodes in PostgreSQL;
the dashboard's alert card uses sample data and is **not** a live alarm display.

These instructions produce a **controlled lab demonstration**, not a production
customer installation. The current MQTT listener and device/gateway MQTT clients
have no TLS, the dashboard and read APIs have no user authentication, credential
provisioning is fixed to demo identities, and backup/restore and fleet operations
are not automated. [The customer deployment guide](04-customer-deployment.md)
names the work and evidence required before a customer rollout.

For component details, see the [firmware](../firmware/README.md),
[gateway](../gateway/README.md), [backend](../backend/README.md), and
[infrastructure](../infra/README.md) guides. Configuration ownership and loading
rules are in [configuration.md](../docs/configuration.md).
