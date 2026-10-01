# Local platform architecture

The root Compose project runs PostgreSQL, Mosquitto, FastAPI, and React/nginx.
The native gateway and firmware run outside Compose so serial access, native
debugging, and the gateway SQLite queue remain independent.

```text
device -> Mosquitto -> native gateway -> FastAPI -> PostgreSQL
                                      <- React/nginx API proxy
```

## Design choices

- PostgreSQL stays on an internal network and is not published to the host.
- Application and MQTT ports bind to loopback unless explicitly changed.
- PostgreSQL and Mosquitto use project-scoped named volumes.
- Backend readiness performs a real database query; liveness is independent.
- nginx serves the frontend and proxies `/api/` on the same origin.
- MQTT requires generated passwords and topic ACLs.
- Database migrations and demo seeding are explicit deployment steps.
- The backend owns PostgreSQL. The gateway owns MQTT intake, SQLite buffering,
  and HTTP forwarding.

Plain HTTP, plaintext MQTT, a shared development database owner, and missing
dashboard login are lab exceptions. See the
[customer release gates](../Setup_Guide/04-customer-deployment.md).

Run `python3 tests/compose_smoke.py` to exercise real containers, SQL, MQTT,
outages, proxy recovery, and volume reuse in an isolated project. Hardware,
gateway power-loss recovery, and backup restoration require separate tests.

Operational commands are in [infra/README.md](../infra/README.md), and settings
are in [configuration.md](configuration.md).
