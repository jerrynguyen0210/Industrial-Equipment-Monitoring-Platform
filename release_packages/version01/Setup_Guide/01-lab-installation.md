# 1. Install and run the lab system

This procedure starts the software stack on one Linux computer. The gateway and
ESP32 are added in [step 2](02-hardware-and-gateway.md). Use the demo identities
only on a controlled lab network; do not ingest customer production data. The
committed PostgreSQL password and the MQTT transport are lab defaults.

## Automated installation

On a 64-bit Raspberry Pi 5 running Raspberry Pi OS, or a 64-bit Debian/Ubuntu
host, run this from an existing repository checkout as your normal user:

```sh
./Setup_Guide/install.sh
```

The script installs Git, Python, Docker Engine, Buildx, and Docker Compose from
Docker's official package repository when required. It then provisions local
MQTT and gateway API credentials, builds and starts the four Compose services,
applies migrations, seeds the demo registry, and checks service health. It does
not print the generated credentials. Existing `.env` files, credentials,
volumes, and database records are validated and reused, so the command is safe
to rerun. The installer supports any other 64-bit Linux distribution when
Python 3, Git, Docker Engine, and Compose v2.24+ are already installed:

```sh
./Setup_Guide/install.sh --skip-host-install
```

Use `--wait-timeout 300` on a slower Pi if containers need more time to become
healthy. Run `./Setup_Guide/install.sh --help` for all options. The script sets
up the local Compose platform only; continue with [step 2](02-hardware-and-gateway.md)
to build the native gateway and configure ESP32 hardware. Services remain bound
to loopback by default, including on a Pi.

## Prepare the host

1. Install and start Docker Engine with the Compose plugin (Compose v2.24 or
   newer), Python 3.13 or newer, Git, and enough disk space for container images
   and persistent readings. Allow at least 2 GB RAM plus build overhead. The
   first build needs internet access. On Windows, use Docker Desktop in Linux
   container mode and adapt the Bash commands to PowerShell; the
   [Windows guide](../docs/docker-testing.md) has examples.
   Use the official Docker installation instructions for
   [Debian](https://docs.docker.com/engine/install/debian/) or
   [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) for the host's
   supported OS; those include the Compose plugin.
2. Obtain this repository on the host and open a terminal at its root. For a
   fresh checkout:

   ```sh
   git clone https://github.com/jerrynguyen0210/Industrial-Equipment-Monitoring-Platform.git
   cd Industrial-Equipment-Monitoring-Platform
   ```

   Confirm
   that host ports 8080, 8000, and 1883 are free. PostgreSQL is not published to
   the host.
3. Verify the tools and the Compose file:

```sh
python3 --version
docker version
docker compose version
docker compose config --quiet
```

`docker version` must show a server as well as a client. The default Compose
project name is `iemp`; keep it stable so subsequent starts reuse the same named
volumes.

## Provision and start

Run the MQTT provisioner **once**. It creates ignored password files for
`device-demo-001`, `gateway-demo-001`, and the broker health account. It refuses
to replace an existing directory; retain that directory across restarts.

```sh
python3 infra/mosquitto/provision.py
docker compose up -d --build --wait
docker compose ps
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m app.seed
docker compose exec -T backend python -m alembic current
```

The explicit migration creates the registry, telemetry, and alert tables. The
seed inserts only `site-demo-001 → gateway-demo-001 → device-demo-001`; ordinary
startup inserts no readings. Apply migrations before starting the gateway.
Expected Alembic head is `0004_temperature_alerts` for this revision.

Check the API and dashboard:

```sh
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8080/api/health/ready
```

Open `http://127.0.0.1:8080/` and `http://127.0.0.1:8080/history`. The demo
device should appear without a recorded reading until an event reaches the
backend. `/ready` must return `{"status":"ready","database":"ok"}`.

## Add the gateway API credential

The gateway needs a bearer token independent of its MQTT password. The backend
rejects ingestion while `GATEWAY_CREDENTIALS_JSON` is empty. Create a unique
token in an ignored, owner-readable file, then put its same value in the two
local configurations described below. Keep both files out of version control.

```sh
mkdir -p secrets
python3 - <<'PY'
import os
import secrets

fd = os.open("secrets/gateway-demo-001.api-token", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as token_file:
    token_file.write(secrets.token_urlsafe(32) + "\n")
PY
cp -n .env.example .env
cp -n gateway/.env.example gateway/.env
chmod 600 .env gateway/.env
```

Edit root `.env`: set `GATEWAY_CREDENTIALS_JSON` to a one-line JSON object with
`gateway-demo-001` as the key and the generated token as the value. For example,
the **shape** is `'{"gateway-demo-001":"<generated-token>"}'`; replace the
placeholder, including its angle brackets. In `gateway/.env`, set
`GATEWAY_API_KEY` to that same token. The exclusive-create command refuses to
replace an existing token file. Do not paste the token into a command, issue
report, or screenshot.

Restart the backend so it loads the map:

```sh
docker compose config --quiet
docker compose up -d --wait --force-recreate backend frontend
```

The frontend rebuilds only when its build settings or code change; the command
above simply ensures its backend dependency is healthy. The gateway config is
used in [step 2](02-hardware-and-gateway.md). Existing `.env` files are kept by
`cp -n`; edit them in place. A shell `GATEWAY_CREDENTIALS_JSON` overrides `.env`.

## Optional isolated verification

The smoke test builds a separate temporary Compose project, checks migrations,
authenticated MQTT, ingestion, outages, and volume reuse, then removes only its
own resources. It does not alter the persistent `iemp` project:

```sh
python3 tests/compose_smoke.py
```

The physical sensor, gateway process, and customer security controls are outside
that test. For normal restarts, use `docker compose up -d --wait`; provisioning
and migrations are repeated only when appropriate. See [operations](03-operations.md).
