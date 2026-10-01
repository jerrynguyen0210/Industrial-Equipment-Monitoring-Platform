# 1. Install and run the lab system

This procedure starts PostgreSQL, Mosquitto, the backend, and the dashboard on
one Linux host. Add the native gateway and ESP32 in [step 2](02-hardware-and-gateway.md).

## Automated installation

1. Use a 64-bit Raspberry Pi OS, Debian, or Ubuntu host with at least 2 GB RAM,
   free ports 8080, 8000, and 1883, and internet access for the first build.
2. Open a terminal at the repository root as your normal user.
3. Run:

   ```sh
   ./Setup_Guide/install.sh
   ```

   The script installs missing host tools, provisions local credentials, starts
   the stack, applies migrations, seeds the demo registry, and checks health.

4. If Docker and the required tools are already managed on the host, run:

   ```sh
   ./Setup_Guide/install.sh --skip-host-install
   ```

5. On a slow host, add `--wait-timeout 300`. Run `--help` for all options.
6. Open `http://127.0.0.1:8080` or the LAN URL printed by the installer.

The installer reuses existing configuration, credentials, volumes, and registry
rows. It does not print generated passwords or tokens.

## Manual installation

Use these steps when the automated installer is unsuitable.

1. Install Git, Python 3, Docker Engine, and Compose v2.24 or newer. Confirm the
   Docker client can reach its server:

   ```sh
   python3 --version
   docker version
   docker compose version
   docker compose config --quiet
   ```

2. Provision local broker accounts once. Keep the generated directory across
   restarts:

   ```sh
   python3 infra/mosquitto/provision.py
   ```

3. Create the gateway API token and local configuration:

   ```sh
   cp -n .env.example .env
   cp -n gateway/.env.example gateway/.env
   ./Setup_Guide/install.sh --skip-host-install
   ```

   The final command safely fills missing local credentials and completes the
   remaining setup. Existing values are preserved.

4. Verify the result:

   ```sh
   docker compose ps
   curl --fail http://127.0.0.1:8000/health
   curl --fail http://127.0.0.1:8000/ready
   curl --fail http://127.0.0.1:8080/api/health/ready
   docker compose exec -T backend python -m alembic current
   ```

   All four services should be healthy. Readiness should return
   `{"status":"ready","database":"ok"}` and Alembic should report the current
   head revision.

## Why the credentials are separate

The ESP32 uses a device password for MQTT and direct heartbeats. The native
gateway has its own MQTT password for subscribing, plus a different bearer token
for backend ingestion. A password from one boundary cannot authenticate another.
Generated files under `secrets/`, root `.env`, and `gateway/.env` are ignored by
Git and must remain private.

## Optional isolated test

```sh
python3 tests/compose_smoke.py
```

This creates a temporary Compose project, tests migrations, MQTT, ingestion,
outages, and data persistence, then removes only its own resources.
