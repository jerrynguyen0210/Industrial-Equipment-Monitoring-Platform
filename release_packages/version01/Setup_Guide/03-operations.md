# 3. Operate and recover the lab system

These commands apply to the controlled lab stack from
[step 1](01-lab-installation.md). Record the running commit, firmware build,
configuration changes, and UTC incident time before changing a failing system.

## Daily checks

```sh
docker compose ps --all
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8080/api/health/ready
docker compose logs --tail 100 postgres mosquitto backend frontend
```

Check gateway `journalctl -u iemp-gateway --since today` if installed as a
service, or its terminal logs otherwise. Look for `subscribed`, queue depth,
`batch_applied`, `delivery_deferred`, and `retry_scheduled`. An increasing queue
means the backend, credentials, network, or storage needs attention. Inspect the
gateway's `quarantined_events` for permanent per-item rejections; they are not
automatically retried. See the [gateway guide](../gateway/README.md) for event
semantics. Check disk space on both the Compose host and the gateway host;
telemetry retention and queue capacity controls have not been implemented.

The dashboard's alert episode card is a standalone sample. For prototype alert
episodes created by real ingestion, query `alert_episodes` as described in
[the alert flow](../docs/temperature-alert-flow.md). There is no live alert
notification or acknowledgement workflow. The backend's current 30°C opening
and 28°C recovery thresholds are constants in code, not site settings.

## Back up before changes

The PostgreSQL and Mosquitto named volumes are live data, not backups. Make a
PostgreSQL logical backup to protected storage with enough free space. The
example uses the active Compose database credentials and writes a custom-format
archive **on the host**; replace the output path with a real protected directory.

```sh
docker compose exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /protected/backups/iemp-YYYYMMDD.dump
```

Check that the file is nonempty and periodically restore it to an **isolated
test database**, then verify registry and telemetry counts. Do not test restore
against the live database. Preserve the root `.env`, broker auth files, firmware
build/configuration, and gateway config in an access-controlled secret store;
they need separate secure handling from the database dump.

The gateway SQLite queue is another durability boundary. Stop the gateway or
use Python's SQLite backup API to copy it consistently. The exact backup and
`PRAGMA quick_check` commands are in the [gateway guide](../gateway/README.md).
Keep the queue, including any pending and quarantined events, through application
upgrades. A power loss can still lose the ESP32's RAM queue; its MQTT PUBACK is
not proof of PostgreSQL persistence.

## Start, stop, and update

```sh
docker compose stop
docker compose up -d --wait
docker compose up -d --build --wait
docker compose exec -T backend python -m alembic upgrade head
```

The first two commands stop/start containers while preserving named volumes.
Use the third after updating application code or images, and run the migration
required by that backend release **before allowing new ingestion**. For a
planned update, record the current revision and backup, stop the gateway, deploy
the backend and migration, validate `/ready`, then restart the gateway and watch
the queue drain. Keep the Compose project name unchanged to reuse its volumes.
`docker compose down` removes containers and networks but retains volumes.
`docker compose down --volumes` deletes database and broker data and must never
be used for routine troubleshooting. Database migration downgrade commands can
also delete data.

## Fault isolation

| Symptom | Check first |
| --- | --- |
| Compose service unhealthy | `docker compose logs --tail 100 <service>` and host disk/port availability. |
| Backend `/ready` returns 503 | PostgreSQL logs, DB credentials, and whether the existing volume has the original password. |
| ESP32 cannot join Wi-Fi | Serial `state=` logs, 2.4 GHz coverage, SSID/passphrase, power. |
| ESP32 connects but no MQTT event | Broker LAN bind/firewall, device password, topic ACL, serial MQTT logs. |
| Gateway not `subscribed` | MQTT address, subscriber password, broker logs, gateway config. |
| `message_stored` without `batch_applied` | Backend reachability, bearer map, gateway retry logs, queue disk space. |
| Dashboard shows an older value | Compare latest database event time and gateway queue; stored value is not a live probe status. |
| Sensor error | Remove power, inspect VDD/GND/DQ and 3.3 V pull-up, then compare against a known probe. |

If a credential changes, update both sides and restart the component that loads
it. The backend loads `GATEWAY_CREDENTIALS_JSON` once at startup. Root `.env`
does not configure the native gateway or firmware. Mosquitto passwords have a
separate [rotation procedure](../infra/README.md#storage-and-shutdown).
