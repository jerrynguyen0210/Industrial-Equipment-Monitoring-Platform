# Local configuration and secrets

Examples contain synthetic local defaults or credential placeholders only.
`docker compose up` still works from a clean checkout without any `.env` file.
Copy an example to `.env` beside it only for the workflow you use, and edit that
local copy. Do not overwrite an existing `.env` when refreshing examples.

## Files and loading rules

| Example | Consumer | Loading and precedence |
| --- | --- | --- |
| [Root](../.env.example) | Compose: PostgreSQL, backend, frontend build, broker publishing | Shell variables override root `.env`, then Compose defaults. A chosen `--env-file` replaces the default file. |
| [Backend](../backend/.env.example) | Native Uvicorn; reference for Alembic/seed | Uvicorn explicitly loads `--env-file .env` from `backend/`; shell variables win. Alembic/seed use exported shell variables only. Nonempty `DATABASE_URL` wins over `PG*`. |
| [Frontend](../frontend/.env.example) | Native Vite | Shell wins, then mode-specific `.env.[mode].local` / `.env.[mode]`, then `.env.local` / `.env`, then code defaults. |
| [Gateway](../gateway/.env.example) | Planned native gateway | Template only; native runtime/env loading is not implemented. API bearer authentication is available. |
| [Simulator](../simulator/.env.example) | Deterministic generator and API-only fixture sender | Reads exported `API_BASE_URL` and `GATEWAY_API_KEY`; `simulate.py --api-base-url` overrides the URL. Scenario options are CLI flags; no automatic `.env` loading. MQTT mode remains planned. |

Compose does **not** automatically load service-directory `.env` files. Application
Docker contexts use allowlists, excluding local env files and secret directories.
Only the public `VITE_API_BASE_URL` is passed to the frontend build. PostgreSQL and
Mosquitto settings belong to the root example and the committed broker config;
firmware has no environment-variable loader yet.

## Local addresses and defaults

| Setting | Local value | Meaning |
| --- | --- | --- |
| `POSTGRES_DB`, `POSTGRES_USER` | `iemp` | Compose database and local owner |
| `POSTGRES_PASSWORD` | `iemp-local-only` | Public synthetic local password; never reuse for deployed data |
| `DATABASE_URL` | Empty in Compose | Uses the `PG*` settings derived from `POSTGRES_*`; explicit URL overrides them |
| Native backend `DATABASE_URL` | `postgresql://iemp:iemp-local-only@127.0.0.1:5432/iemp` | Requires a separately provisioned host database |
| `VITE_API_BASE_URL` | `/api` | Browser API prefix; readiness appends `/health/ready` |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Native Vite development proxy target, without `/api` |
| `MQTT_HOST`, `MQTT_PORT` | `127.0.0.1`, `1883` | Planned native gateway/simulator broker address |
| `API_BASE_URL` | `http://127.0.0.1:8000/api` | Gateway/simulator API prefix |
| `GATEWAY_API_KEY` | `replace-with-provisioned-...-credential` | Nonfunctional placeholder; replace with a generated token matching the backend map |
| `GATEWAY_CREDENTIALS_JSON` | Empty | Backend map of registered gateway IDs to unique bearer tokens; empty denies ingestion |
| Root `FRONTEND_PORT`, `BACKEND_PORT`, `MQTT_PORT` | `8080`, `8000`, `1883` | Published host ports, not container ports |
| Root `*_BIND_ADDRESS` | `127.0.0.1` | Loopback publishing |

Inside Compose the database is `postgres:5432`, the broker is `mosquitto:1883`, and
the API is `backend:8000`. Those DNS names do not work in host processes or
browsers. Compose does not publish PostgreSQL. A Pi uses the development host's
reachable LAN address rather than its own loopback; see the
[hardware connectivity instructions](../infra/README.md#gateway-and-firmware-outside-compose).

For an explicit Compose database URL, set `DATABASE_URL` in the root `.env` with
`postgres:5432` and credentials matching `POSTGRES_*`. Changing `POSTGRES_PASSWORD`
does not update an explicit URL or rotate an existing database password. Follow
the [existing-volume rotation procedure](../infra/README.md#storage-and-shutdown).
An external URL changes only the backend connection; Compose still starts its
local PostgreSQL dependency.

URL-encode special characters in URL usernames/passwords (for example, `@` becomes
`%40`, `:` becomes `%3A`, and `$` becomes `%24`). Do not concatenate raw secrets
into a URL. For root Compose values containing literal `$` or `#`, single-quote
the value in `.env` to avoid interpolation/comment parsing. `PG*` variables remain
an alternative to URL encoding. Configuration errors and readiness logs omit
connection values.

The backend loads `GATEWAY_CREDENTIALS_JSON` once at startup. Use a JSON object
whose keys are registered gateway IDs and values are generated tokens. No default
gateway token is provisioned. Invalid mappings fail startup with a value-free
error. Removing/replacing a mapping and restarting the backend revokes/rotates
its credential; gateway/site disabling in the registry applies on the next
ingestion request. The [simulator quick start](../simulator/README.md) generates
a local token without printing it and provisions the demo mapping explicitly.

## Local setup

For Compose, from the repository root:

```sh
cp .env.example .env
# Edit local overrides, then validate without printing resolved secrets.
docker compose config --quiet
docker compose up -d --build --wait
```

In PowerShell, `Copy-Item .env.example .env` is the equivalent copy command.
Native backend and frontend commands are in their respective READMEs. Uvicorn's
`--env-file` support uses the locked `python-dotenv` development dependency.
Restart native processes after changing settings; rebuild the frontend after
changing `VITE_API_BASE_URL`. Nginx runtime variables do not modify built assets.

Keep `/api` for local browser access through Vite/Nginx. An absolute browser API
URL must be reachable by the browser and permit that frontend origin through
CORS; the current backend does not configure cross-origin access.

## Secret handling

Never store real database URLs, gateway keys, private keys, or service-account
credentials in examples, source, test fixtures, logs, or screenshots. All `VITE_*`
values and frontend build arguments are public; credentials belong in backend or
gateway runtime configuration. Prototype API bearer authentication uses the
explicit backend credential map; placeholder tokens are rejected. The broker
still permits anonymous, unencrypted local MQTT.

Git ignores `.env` and variants, `*.env` files, `secrets/`, `.secrets/`,
`credentials/`, common private-key/keystore files, `.pgpass`, and service-account
credential files. Sanitized `.env.example` files stay trackable. Keep other local
credential formats under `secrets/` and restrict access using host permissions.
Git ignores do not protect a file already tracked: if a real secret was committed,
revoke/rotate it and arrange history cleanup; deleting the working file alone is
insufficient. Do not share expanded `docker compose config` output or environment
dumps; use `--quiet` for validation.

Loading behavior follows the official [Compose interpolation documentation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
and [Vite environment documentation](https://vite.dev/guide/env-and-mode).
