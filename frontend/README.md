# Frontend

The React/TypeScript dashboard shell for the local monitoring platform.

## Development guide

Read [Frontend Coding Conventions](CODING_CONVENTIONS.md) for component design,
API integration, telemetry presentation, accessibility, security, and testing.

## Setup and validation

The app uses React, strict TypeScript, Vite, Node.js 24.15+ (below 25), and npm
with a committed lockfile. Overview (`/`), History (`/history`), and Service
Status (`/status`) share the dashboard layout. Overview fetches registered
devices and their latest stored temperatures from `GET /api/v1/devices`, with explicit
loading, empty, and error states. Service Status displays backend/database
readiness. History queries the [backend history API](../docs/history-api.md),
plots measurement-time points with visible gaps, and lets operators switch
between UTC and local display. Alert evaluation is not implemented; active alert
counts are shown as unavailable.

From the repository root, provision local MQTT credentials once, then build and
start Compose:

```powershell
python infra/mosquitto/provision.py
docker compose up -d --build --wait
```

Open http://localhost:8080. An unprivileged Nginx container serves the frontend;
browser requests to `/api/` are forwarded to the backend over the Compose network.
The browser never needs container DNS names, CORS configuration, or database
credentials. Nginx re-resolves the backend name so container replacement can
recover automatically.
The provisioner refuses to replace an existing credential directory; on later
starts, run only the Compose command. The isolated `python tests/compose_smoke.py`
test provisions its own MQTT credentials.

For frontend development, start the backend from the repository root with
`docker compose up -d --build --wait backend`. Then in `frontend/`:

```powershell
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). Vite proxies `/api`
to `http://127.0.0.1:8000`; set `API_PROXY_TARGET` in `frontend/.env` if you override
`BACKEND_PORT`. Copy `.env.example` to `.env` only when changing defaults, and
restart Vite after changing the file.

`VITE_API_BASE_URL` defaults to `/api`; it includes the API prefix, and a trailing
slash is optional. For an absolute URL, use a browser-reachable address with the
API prefix and configure CORS on that API. The current backend has no cross-origin
allowlist, so the same-origin proxy is the working local default.

Vite loads `frontend/.env` for native development/builds. Compose instead passes
`VITE_API_BASE_URL` from the root `.env` as a Docker build argument; run
`docker compose up -d --build frontend` after changes. Setting an environment
variable on an already-built Nginx container cannot change the bundle. All
`VITE_*` values are public: never put database passwords or gateway credentials
there. See the [configuration guide](../docs/configuration.md).

```powershell
npm run check
npm test
npm run build
```

`check` runs TypeScript and Prettier, including the test code and configuration.
`test` runs Vitest once with React Testing Library and jsdom; a failed test or an
empty suite returns a nonzero exit code. `npm run test:watch` reruns tests during
development. Tests use mocked HTTP responses and controlled timers to cover
loading, readiness validation, outages, automatic recovery, request timeouts,
unmount cleanup, and StrictMode polling. They need no running backend or Docker.

`build` produces `dist/`; the Docker build copies that output into Nginx.
`npm run format` applies formatting. Container health checks `/healthz`,
independently of backend availability; the status view polls backend readiness
every five seconds after the preceding request completes, times out failed
requests, and recovers automatically.

The [CI workflow](../.github/workflows/local-platform.yml) runs these checks on
every push and pull request. See the [CI guide](../docs/ci.md) for dependency
caches, integration checks, and failure handling.

Coordinate API contracts and interface decisions in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
