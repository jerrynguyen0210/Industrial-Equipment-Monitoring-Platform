# Frontend

React and TypeScript dashboard for devices, current temperature, history, service
health, and device registration/removal.

## Run locally

1. Use Node.js 24 (below 25).
2. From `frontend/`, install the locked dependency graph:

   ```sh
   npm ci
   ```

3. Copy settings only when overriding defaults:

   ```sh
   cp -n .env.example .env
   npm run dev
   ```

4. Open the Vite URL. `/api` is proxied to `API_PROXY_TARGET`, which defaults to
   `http://127.0.0.1:8000`.

For the container version, run `docker compose up -d --build frontend` from the
repository root and open `http://localhost:8080`.

## Device registration

The Device Management page lists persistent registrations from PostgreSQL.
Registering a device also creates its Mosquitto account. Configure the ESP32 with
the exact same Device ID and password. Removing a device revokes managed MQTT
credentials, but the backend refuses deletion while telemetry or alerts exist.

Online means the backend accepted a heartbeat or recent telemetry within 90
seconds. It does not diagnose power, Wi-Fi, MQTT, gateway, or sensor faults.

## Run the checks

```sh
npm run check
npm test
npm run build
```

`check` runs formatting and TypeScript validation. Tests use mocked HTTP and fake
timers; the production build verifies the nginx-served assets. Follow
[Frontend Coding Conventions](CODING_CONVENTIONS.md).
