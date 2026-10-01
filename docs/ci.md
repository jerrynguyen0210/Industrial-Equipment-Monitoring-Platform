# Continuous integration

The [local platform workflow](../.github/workflows/local-platform.yml) runs on
every push, pull request update, tag, and manual dispatch.

## Checks

| Job | Main checks | Timeout |
| --- | --- | --- |
| Backend | Locked install, Ruff, unit tests, PostgreSQL migration/ingestion suites. | 10 min |
| Frontend | `npm ci`, formatting, TypeScript, component tests, production build. | 10 min |
| Compose | Isolated container smoke test with PostgreSQL and Mosquitto. | 20 min |
| Gateway | clang-format, C++17 build, lifecycle, MQTT intake, and HTTP delivery tests. | 10 min |

Jobs run independently on Ubuntu 24.04. A failed command fails its job; no check
uses `continue-on-error`. Actions use pinned commits, and Python/npm dependencies
use committed lockfiles. Caches speed downloads but never replace installation
or verification.

The Compose job creates unique credentials, ports, project name, databases, and
volumes, then removes them. CI uses no repository secrets or physical hardware.

## Reproduce a failure

1. Start from a clean checkout with Python 3.13 and Node.js 24.
2. Run backend and PostgreSQL checks from
   [backend/README.md](../backend/README.md#run-the-checks).
3. Run frontend checks:

   ```sh
   cd frontend
   npm ci
   npm run check
   npm test
   npm run build
   ```

4. Run the Compose check from the repository root:

   ```sh
   docker compose config --quiet
   python3 tests/compose_smoke.py
   ```

5. Run native gateway checks from
   [gateway/README.md](../gateway/README.md#build-and-test).

For one Sprint 1 QA file, set `REGISTRY_TEST_DATABASE_URL`, change to `backend/`,
and run:

```sh
python -m unittest discover -s tests/integration -p test_sprint1_qa.py -v
```

The QA matrix covers valid storage, duplicate replay, identity conflict, mixed
outcomes, lost acknowledgements, invalid values, null measurement time, historical
events, out-of-order arrival, and identity reuse after reboot.

In GitHub, open the commit or pull request **Checks** tab and inspect the first
failed step. Branch rules must separately require all four jobs before merge.
