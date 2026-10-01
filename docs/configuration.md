# Configuration and secrets

Copy an example only for the workflow you use. Never overwrite an existing local
file or commit secret values.

## Configuration owners

| Example | Consumer | Loading rule |
| --- | --- | --- |
| [`.env.example`](../.env.example) | Compose | Shell values override root `.env`, then Compose defaults. |
| [`backend/.env.example`](../backend/.env.example) | Native Uvicorn | Pass explicitly with `--env-file`; Alembic and seed use exported variables. |
| [`frontend/.env.example`](../frontend/.env.example) | Native Vite | Vite mode file precedence; shell values win. |
| [`gateway/.env.example`](../gateway/.env.example) | Native gateway | Pass with `--config`; shell values win; relative paths start at the config directory. |
| [`simulator/.env.example`](../simulator/.env.example) | Simulator | Environment and CLI flags; no automatic `.env` loading. |
| [`firmware/sdkconfig`](../firmware/README.md) | ESP32 | Created by `idf.py menuconfig`; rebuild and flash after a change. |

Compose does not load component `.env` files. Docker build allowlists exclude
local configuration and secret directories.

## Main local settings

| Setting | Default or rule |
| --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER` | `iemp` |
| `POSTGRES_PASSWORD` | Public lab-only default; replace for any real data. |
| `DATABASE_URL` | When set, overrides all `PG*` values. |
| `VITE_API_BASE_URL` | `/api` |
| `MQTT_HOST`, `MQTT_PORT` | `127.0.0.1:1883` for host clients. |
| `API_BASE_URL` | `http://127.0.0.1:8000/api` for gateway/simulator. |
| `QUEUE_DB_PATH` | Persistent gateway SQLite path. |
| `GATEWAY_CREDENTIALS_JSON` | Backend map from gateway IDs to bearer tokens. Empty denies ingestion. |
| `GATEWAY_API_KEY` | Gateway token matching the backend map. |
| `*_BIND_ADDRESS` | `127.0.0.1`; use an explicit LAN address only for a controlled lab. |

Inside Compose, use `postgres:5432`, `mosquitto:1883`, and `backend:8000`.
Those names do not work from a browser, ESP32, or native host process. Such
clients use `127.0.0.1` on the same host or the server's LAN address.

## Set up local configuration

1. Run the installer when possible:

   ```sh
   ./Setup_Guide/install.sh
   ```

2. For a manual Compose setup, copy the root example only when overrides are
   needed:

   ```sh
   cp -n .env.example .env
   chmod 600 .env
   ```

3. Validate without printing resolved secrets:

   ```sh
   docker compose config --quiet
   ```

4. Restart a process after changing its configuration. The backend loads gateway
   credentials once at startup; firmware settings require rebuild and flash.

## Difficult cases

- URL-encode special characters in `DATABASE_URL`; using separate `PG*` fields
  avoids URL encoding.
- Changing `POSTGRES_PASSWORD` does not rotate a password in an existing volume.
- Quote Compose `.env` values containing `$` or `#` to prevent interpolation or
  comments.
- A device registration password authenticates that device's MQTT and heartbeat
  requests. It is unrelated to the gateway subscriber password and gateway API
  bearer token.
- Registration automatically manages device broker accounts. The initial
  provisioner still creates demo, gateway, and health accounts.

Configuration errors and logs must never print secret values. Keep `.env`,
`sdkconfig`, firmware images, broker password files, API tokens, and gateway
queue backups in access-controlled storage.
