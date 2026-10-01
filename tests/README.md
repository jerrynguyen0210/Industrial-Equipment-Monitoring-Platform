# Shared tests

Cross-component fixtures and tests. Component unit tests stay with their code.

## Telemetry contract scenarios

`telemetry_scenarios.py` runs eight independent cases from
`fixtures/telemetry-scenarios.json`:

| Scenario | Expected behavior |
| --- | --- |
| Duplicate | First accepted, identical retry duplicate. |
| Identity conflict | Changed content rejected; original remains. |
| Invalid unit | Rejected without storage. |
| Malformed value | Invalid JSON value types rejected per item. |
| Unknown device | Rejected without storage. |
| Stale timestamp | Historical event accepted for storage. |
| Out-of-order sequence | Events accepted; arrival order is not identity order. |
| Mixed batch | Ordered accepted, duplicate, conflict, validation, ownership outcomes. |

Generate fixtures without services:

```sh
python3 tests/telemetry_scenarios.py --list
python3 tests/telemetry_scenarios.py --export-only --run-id review-01
```

Run against a dedicated migrated/seeded test backend:

```sh
export API_BASE_URL=http://127.0.0.1:8000/api
export GATEWAY_API_KEY='<test-gateway-token>'
python3 tests/telemetry_scenarios.py
```

The runner exports exact requests and a JSON report under ignored
`test-results/telemetry/`. It never retries or changes identity. Use a new run ID
for fresh accepted outcomes. Credentials are not written to reports.

## Full Compose smoke test

1. Start Docker.
2. From the repository root, run:

   ```sh
   docker compose config --quiet
   python3 tests/compose_smoke.py
   ```

The suite creates a random isolated project, credentials, ports, and volumes. It
tests health, migrations, registry seed, MQTT ACLs, simulator MQTT/HTTP paths,
all contract scenarios, PostgreSQL values, backend/database outages, proxy
recovery, and persistence across restart. Cleanup removes only test resources.

The smoke test does not exercise physical hardware or the native gateway. Run
the [gateway outage demo](../gateway/README.md#demonstrate-outage-recovery) for
the SQLite-to-backend recovery path.

## Run test code checks

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
python -m ruff check --config backend/pyproject.toml backend simulator tests
python -m ruff format --check --config backend/pyproject.toml backend simulator tests
```

See [Shared Testing Coding Conventions](CODING_CONVENTIONS.md) and
[docs/ci.md](../docs/ci.md).
