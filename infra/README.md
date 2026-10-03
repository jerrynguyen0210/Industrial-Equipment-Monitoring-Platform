# Infrastructure

Compose runs PostgreSQL 17, Mosquitto, the FastAPI backend, and the React/nginx
frontend. Firmware and the native gateway run outside Compose.

## Start and verify

1. From the repository root, run the installer:

   ```sh
   ./Setup_Guide/install.sh
   ```

2. Or perform the basic manual start:

   ```sh
   python3 infra/mosquitto/provision.py
   docker compose up -d --build --wait
   docker compose exec -T backend python -m alembic upgrade head
   docker compose exec -T backend python -m app.db.seed
   ```

3. Verify:

   ```sh
   docker compose ps
   curl --fail http://127.0.0.1:8000/ready
   curl --fail http://127.0.0.1:8080/api/health/ready
   ```

The provisioner refuses to replace an existing auth directory. Retain it across
restarts. The demo seed is optional and must not be used for customer data.

## Addresses and network

| Service | Default host address |
| --- | --- |
| Dashboard | `http://127.0.0.1:8080` |
| Backend | `http://127.0.0.1:8000` |
| MQTT | `127.0.0.1:1883` |
| PostgreSQL | Internal only |

For an ESP32 or separate gateway, bind MQTT/backend to the server's specific LAN
address and configure clients with that address. Do not use `0.0.0.0` as a client
destination. Plain MQTT and device heartbeat HTTP are lab-only transports.

The frontend proxies `/api` to the backend. PostgreSQL is reachable only on the
internal network. A backend outage does not stop Mosquitto or the static frontend.

## Device broker accounts

The dashboard registration API creates device accounts and topic ACLs. The
initial provisioner creates only the demo device, gateway subscriber, and health
accounts needed to boot and test the lab. Removing a managed device revokes its
broker account when it has no retained history.

The native gateway uses its MQTT password to subscribe and a separate bearer
token to send HTTP batches. Keep both private.

## Storage and shutdown

PostgreSQL and Mosquitto use named volumes. Operate them with:

```sh
docker compose stop
docker compose up -d --wait
docker compose down
```

`down` removes containers and networks but retains named volumes. Adding
`--volumes` deletes stored database and broker data.

To rotate the PostgreSQL password in an existing volume, change it inside
PostgreSQL and update every matching connection setting in the same maintenance
window. Changing `.env` alone affects only container configuration, not the
stored database role.

Back up PostgreSQL with `pg_dump` and test restore in isolation. Broker volumes
and the gateway SQLite queue are separate durability boundaries and require
their own backup plan.

## Troubleshoot

1. Run `docker compose ps --all`.
2. Inspect bounded logs: `docker compose logs --tail 100 <service>`.
3. Check host ports and disk space.
4. Re-run `docker compose config --quiet` after configuration changes.
5. Confirm a device/gateway uses the server LAN address and the correct type of
   credential.

Do not delete volumes as a troubleshooting step. See
[Infrastructure Coding Conventions](CODING_CONVENTIONS.md).
