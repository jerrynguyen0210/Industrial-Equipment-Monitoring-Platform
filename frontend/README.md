# Frontend

Equipment dashboards, telemetry views, and user-facing monitoring workflows.

## Development guide

Read [Frontend Coding Conventions](CODING_CONVENTIONS.md) for component design,
API integration, telemetry presentation, accessibility, security, and testing.

## Setup and validation

The bootstrap uses React, strict TypeScript, Vite, Node.js 24, and npm with a
committed lockfile. It displays backend/database readiness, loading, and outage
states. Equipment data, history, and alerts are not implemented yet.

From the repository root, `docker compose up` builds the frontend and serves it at
http://localhost:8080 through an unprivileged Nginx container. Browser requests to
`/api/` are forwarded to the backend over the Compose network. The browser never
needs container DNS names, CORS configuration, or database credentials. Nginx
re-resolves the backend name so container replacement can recover automatically.

For frontend development, start the backend using Compose, then in `frontend/`:

```sh
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). Vite proxies `/api`
to `http://127.0.0.1:8000`; adjust `vite.config.ts` if you override `BACKEND_PORT`.

```sh
npm run check
npm run build
```

`check` runs TypeScript and Prettier. `build` produces `dist/`; the Docker build
copies that output into Nginx. `npm run format` applies formatting. Container
health checks `/healthz`, independently of backend availability; the status page
polls backend readiness every five seconds after the preceding request completes,
times out failed requests, and recovers automatically.

Coordinate API contracts and interface decisions in [docs/](../docs/README.md).
Follow the shared [conventions](../CONTRIBUTING.md).
