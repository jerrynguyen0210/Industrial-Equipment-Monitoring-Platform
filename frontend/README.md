# Frontend

Equipment dashboards, telemetry views, and user-facing monitoring workflows.

## Development guide

Read [Frontend Coding Conventions](CODING_CONVENTIONS.md) for component design,
API integration, telemetry presentation, accessibility, security, and testing.

## Setup and validation

The bootstrap uses React, strict TypeScript, Vite, Node.js 24.15+ (below 25), and
npm with a committed lockfile. It displays backend/database readiness, loading, and outage
states. Equipment data, history, and alerts are not implemented yet.

From the repository root, `docker compose up` builds the frontend and serves it at
http://localhost:8080 through an unprivileged Nginx container. Browser requests to
`/api/` are forwarded to the backend over the Compose network. The browser never
needs container DNS names, CORS configuration, or database credentials. Nginx
re-resolves the backend name so container replacement can recover automatically.

For frontend development, start the backend using Compose, then in `frontend/`:

```sh
npm ci
cp .env.example .env
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). Vite proxies `/api`
to `http://127.0.0.1:8000`; set `API_PROXY_TARGET` in `frontend/.env` if you override
`BACKEND_PORT`. Restart Vite after changing the file.

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

```sh
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
`npm run format` applies formatting. Container
health checks `/healthz`, independently of backend availability; the status page
polls backend readiness every five seconds after the preceding request completes,
times out failed requests, and recovers automatically.

The [CI workflow](../.github/workflows/local-platform.yml) runs these checks on
every push and pull request. See the [CI guide](../docs/ci.md) for dependency
caches, integration checks, and failure handling.

Coordinate API contracts and interface decisions in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
