# Infrastructure

Local environment configuration and platform deployment definitions.

## Development guide

Read [Infrastructure Coding Conventions](CODING_CONVENTIONS.md) for configuration,
environment isolation, secrets, deployment, persistent storage, and recovery.

## Start the local platform

Install Docker Engine and Compose v2.24+ (or Docker Desktop with Linux
containers), start the daemon, and run from the repository root:

```sh
docker compose up
```

No native compiler, Python, Node.js, hardware, or pre-existing `.env` is needed.
The first start needs internet access to download images and locked packages.
Images are pinned by digest; application dependencies use committed lockfiles.
To update images, deliberately refresh the digests and rerun the smoke test.

Open http://localhost:8080. For a background start that fails when services do not
become healthy, use `docker compose up -d --wait --wait-timeout 120`. Image build
time is separate from service startup time. Use `docker compose up --build` after
changing application source, dependencies, or Dockerfiles.

## Configuration and network

The root [compose.yaml](../compose.yaml) defines exactly four services. All use
bounded container logs (three files of up to 10 MB), CPU/memory limits, an
`unless-stopped` restart policy, and a 20-second graceful-stop timeout. Resource
limits total 1 GiB of container memory; allow at least 2 GB plus build overhead.

| Service | Container address | Host access | Health check |
| --- | --- | --- | --- |
| PostgreSQL | `postgres:5432` | None | `pg_isready` over TCP |
| Mosquitto | `mosquitto:1883` | `127.0.0.1:1883` | MQTT QoS 1 publish with a deadline |
| Backend | `backend:8000` | http://localhost:8000 | `/ready`, including a database query |
| Frontend | `frontend:8080` | http://localhost:8080 | Nginx `/healthz` |

The `database` network is explicitly internal and contains only PostgreSQL and
the backend. The `platform` bridge connects the backend, frontend, and broker and
supports their published host ports. Compose DNS names are for containers;
native gateway processes and browsers use host addresses. PostgreSQL has no
published host port. There are no fixed container names or external networks to
create beforehand.

PostgreSQL readiness gates backend startup; backend readiness gates frontend
startup. Mosquitto starts independently and never depends on the backend. Health
checks report availability; Docker does not restart a process merely because it
is unhealthy. Once running, the frontend continues serving its page during an
API outage and the backend reconnects after database recovery.

Copy [.env.example](../.env.example) to `.env` only to override defaults. Shell
environment variables take precedence over `.env`, followed by the defaults in
Compose. `.env` is ignored by Git and excluded from application image contexts.

| Setting | Default | Purpose |
| --- | --- | --- |
| `POSTGRES_DB` / `POSTGRES_USER` | `iemp` / `iemp` | Initial database and local owner |
| `POSTGRES_PASSWORD` | `iemp-local-only` | Local-only password shared with the backend |
| `DATABASE_URL` | Empty | Optional backend PostgreSQL URL; overrides its `PG*` settings |
| `VITE_API_BASE_URL` | `/api` | Public browser API prefix, applied during frontend build |
| `FRONTEND_PORT` / `BACKEND_PORT` / `MQTT_PORT` | `8080` / `8000` / `1883` | Published host ports |
| `FRONTEND_BIND_ADDRESS` / `BACKEND_BIND_ADDRESS` / `MQTT_BIND_ADDRESS` | `127.0.0.1` | Host interfaces to publish on |

Changing a host port does not change the service's internal port. The frontend's
same-origin API proxy therefore continues working if `BACKEND_PORT` changes.
Native clients must update their own MQTT port or API/proxy address when a host
port changes. The root example owns PostgreSQL and broker publishing settings;
Mosquitto's listener/anonymous access remain explicit in
`infra/mosquitto/mosquitto.conf`, which does not read `.env`. See the
[configuration guide](../docs/configuration.md) for service templates and precedence.
Plain HTTP, anonymous MQTT, and a shared development database owner/password are
explicit local-only exceptions. Do not use this configuration as a deployed
environment or place production data in it. No secrets are shipped to the browser.

## Storage and shutdown

| Named volume | Mount | Owner / purpose |
| --- | --- | --- |
| `postgres_data` | `/var/lib/postgresql/data` | Official image's `postgres` user; database files |
| `mosquitto_data` | `/mosquitto/data` | Official image's `mosquitto` user; retained messages/session state |

The official entrypoints initialize volume permissions; no manual host `chmod`
is needed. Backend and frontend run as unprivileged users. Mosquitto configuration
is a read-only file mount; broker logs go to stdout rather than an unbounded volume.
Volume names are Compose-project scoped (normally `iemp_postgres_data` and
`iemp_mosquitto_data`). Keep the project name stable to reuse data.

```sh
docker compose stop         # Stop processes and preserve containers and data.
docker compose down         # Remove containers/networks and preserve data.
docker compose up -d --wait # Recreate containers and reuse the same data.
```

Only for an intentional reset of the current local project, the following
**deletes both named volumes and their data**:

```sh
docker compose down --volumes
```

PostgreSQL initialization settings only apply to an empty volume. Changing a
password in `.env` does not rotate the database password. For existing data,
connect with `docker compose exec postgres psql -U iemp -d iemp`, use
`\password iemp`, update `.env` to match, and recreate the backend. Adjust the user/database
names when customized. Do not delete a valuable volume to resolve credentials.

Mosquitto saves persistence periodically (30 seconds) and on a graceful shutdown.
A broker acknowledgement is not proof of gateway SQLite commit or immediate
disk durability. Neither volume is a backup; backup/restore automation and
telemetry retention are outside this bootstrap. Monitor Docker disk usage with
`docker system df`; named volumes have no portable Compose disk quota.

## Gateway and firmware outside Compose

Gateway C++17/SQLite and ESP-IDF firmware remain native workstreams. Neither is
built or started by Compose, and there are no privileged containers or device
mounts. Keep the gateway queue on the gateway's persistent local filesystem,
outside this Compose project's volumes. Native build/flash/run commands will be
added by those workstreams when their implementations exist.

For a gateway process on the same computer, configure MQTT at `127.0.0.1:1883`
and the backend base URL at `http://127.0.0.1:8000`. The intended ingestion route
is not implemented yet; `/ready` can verify connectivity now.

For an ESP32 or Raspberry Pi on a trusted lab LAN, set `MQTT_BIND_ADDRESS` in
`.env` to the development computer's LAN IPv4 address. If a Pi gateway also needs
the API, set `BACKEND_BIND_ADDRESS` to that address. Recreate the relevant service
with `docker compose up -d`. Use that LAN address in device configuration, and
allow only the intended clients through the host firewall. `localhost` on a Pi
refers to the Pi, and `mosquitto` is not a LAN DNS name. MQTT is anonymous and
unencrypted in this local configuration; deployed device authentication/TLS is a
separate task. Keep dashboard publishing on loopback unless needed.

With native Mosquitto client tools, run these in two host terminals to exercise
the host-to-broker path (substitute the LAN address when testing remotely):

```sh
mosquitto_sub -h 127.0.0.1 -p 1883 -t iemp/dev/connectivity -q 1 -C 1 -W 30
mosquitto_pub -h 127.0.0.1 -p 1883 -t iemp/dev/connectivity -q 1 -m connected
```

For hardware work without the application stack, run `docker compose up -d
mosquitto`. To simulate a backend outage while MQTT remains available:

```sh
docker compose stop backend
# Continue native MQTT publishing/subscribing here.
docker compose up -d --wait backend
```

Do not use `docker compose down` for a backend-only outage: it also stops the
broker. A gateway on a Pi may instead use a native Pi broker while this Compose
stack supplies only PostgreSQL/backend/frontend.

## Validation and troubleshooting

```sh
docker compose config --quiet
docker compose ps --all
docker compose logs --tail 100 postgres mosquitto backend frontend
python tests/compose_smoke.py
```

The Python smoke test needs Python 3.13+ and a running Docker daemon. It uses a
unique project, random host ports, synthetic data, and temporary credentials;
it verifies outages and named-volume persistence before removing only its own
test volumes. See [tests/README.md](../tests/README.md).

- Daemon unavailable: start Docker Desktop/Engine and verify `docker info`.
- Port conflict: change the corresponding `*_PORT` in `.env`, then recreate.
- Backend unhealthy: inspect database/API logs; verify existing-volume credentials.
- Frontend shows unavailable: inspect backend readiness; it needs an actual SQL
  query, while `pg_isready` only confirms that PostgreSQL accepts connections.
- Broker mount error: confirm `infra/mosquitto/mosquitto.conf` is a file and Docker
  Desktop can share the checkout. Compose will not create a missing config directory.
- Pi/ESP32 cannot connect: verify the explicit bind address, host firewall, LAN
  reachability, and that clients use the computer's address rather than localhost.

Compose behavior follows the official [startup ordering](https://docs.docker.com/compose/how-tos/startup-order/)
and [network configuration](https://docs.docker.com/reference/compose-file/networks/)
documentation. Broker persistence and queue settings follow the
[Mosquitto configuration reference](https://mosquitto.org/man/mosquitto-conf-5.html).
