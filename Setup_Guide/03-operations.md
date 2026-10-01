# 3. Operate and recover the lab system

## Daily check

1. Check services and readiness:

   ```sh
   docker compose ps --all
   curl --fail http://127.0.0.1:8000/ready
   curl --fail http://127.0.0.1:8080/api/health/ready
   docker compose logs --tail 100 postgres mosquitto backend frontend
   ```

2. Check gateway logs with `journalctl -u iemp-gateway --since today`, or inspect
   its terminal.
3. Investigate a growing queue, repeated `delivery_deferred`, or quarantined
   events. Check disk space on the server and gateway.

The dashboard alert card uses sample data. Query `alert_episodes` for prototype
backend alerts; see [the alert contract](../docs/temperature-alert-flow.md).

## Back up before a change

1. Write a PostgreSQL dump to protected host storage:

   ```sh
   docker compose exec -T postgres sh -c \
     'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
     > /protected/backups/iemp-YYYYMMDD.dump
   ```

2. Confirm the file is nonempty.
3. Restore it periodically into an isolated test database and compare registry
   and telemetry counts.
4. Stop the gateway or use the SQLite backup procedure in the
   [gateway guide](../gateway/README.md#back-up-and-check-the-queue).
5. Store `.env`, broker auth files, gateway config, and firmware configuration
   in an approved secret store; they are not part of the database dump.

Named volumes provide persistence, but they are not backups.

## Update safely

1. Record the current revision and create a backup.
2. Stop the gateway so it queues no data against a changing schema.
3. Rebuild and start services:

   ```sh
   docker compose up -d --build --wait
   docker compose exec -T backend python -m alembic upgrade head
   ```

4. Verify `/ready` and the migration head.
5. Restart the gateway and watch its queue drain.

Use `docker compose stop` and `up -d --wait` for routine restarts. `docker compose
down` keeps named volumes. `docker compose down --volumes` deletes database and
broker data and must not be used for troubleshooting.

## Fault guide

| Symptom | Check |
| --- | --- |
| Service unhealthy | `docker compose logs --tail 100 <service>`, disk, and ports. |
| `/ready` returns 503 | PostgreSQL logs and database credentials. |
| ESP32 cannot join Wi-Fi | 2.4 GHz coverage, SSID/password, power, and serial logs. |
| ESP32 has no MQTT connection | Broker LAN bind, firewall, Device ID/password, and topic ACL. |
| Gateway is not subscribed | Gateway MQTT address/password and broker logs. |
| `message_stored` without `batch_applied` | Backend URL/token, retry logs, and queue storage. |
| Device appears offline | Heartbeat config, recent accepted telemetry, and the 90-second window. |
| Sensor error | Power off, inspect VDD/GND/DQ and pull-up, then test a known probe. |

After changing a credential, update both ends and restart the component that
loads it. Root `.env` does not configure the native gateway or firmware.
