# Continuous integration

The [Local platform workflow](../.github/workflows/local-platform.yml) runs for
every branch and tag push, every pull request update, and manual
`workflow_dispatch` runs. There are no branch or path filters. GitHub's manual
Run workflow button becomes available when the workflow is on the default branch.

## Automated checks

Jobs run independently on Ubuntu 24.04 so a failure in one workstream does not
prevent the other jobs from producing useful results.

| Check | Verification | Runtime and limit |
| --- | --- | --- |
| Backend lint and tests | Hash-locked dependencies, Ruff lint/format, backend, simulator and shared QA fixture/CLI tests, and registry/telemetry/HTTP ingestion tests against PostgreSQL 17. Python lint also covers the simulator and all shared test scripts. | Python 3.13; 10 minutes. |
| Frontend checks, tests, and build | `npm ci`, TypeScript and Prettier checks, `npm test`, production build. | Node.js 24; 10 minutes. |
| Compose integration | Compose configuration validation and the isolated smoke suite against actual backend/frontend images, PostgreSQL, and Mosquitto. | Python 3.13 and Docker Compose; 20 minutes. |
| Gateway build and intake tests | clang-format 18 check, CMake Release build, lifecycle tests, and authenticated MQTT intake against a temporary broker. | Runner CMake, C++ compiler, SQLite/Mosquitto/JSON headers, Python 3, and Mosquitto tools; 10 minutes. |

Every install, lint, test, and build command must succeed. No check uses
`continue-on-error`, suppresses an error exit code, or retries a failed suite.
Frontend tests run once with `vitest run`; an empty suite fails. Steps after a
failure in the same job are skipped and the job stays failed. Other jobs continue.
Job timeouts also prevent a hung build or test from being reported as successful.

The gateway job installs native development headers and Mosquitto tools, builds
the C++17 executable, and runs lifecycle and broker-backed intake tests. These
checks cover local startup, clean shutdown, valid and invalid MQTT events, and
receipt-time persistence. HTTP forwarding, hardware behavior, and power-loss
recovery remain untested.

## Repeatability and caches

- GitHub Actions are pinned to full commit SHAs. Runner OS and language major/minor
  versions are explicit. Python and Node dependency versions are committed in
  lockfiles; the native gateway uses the runner distribution's CMake, SQLite,
  Mosquitto, JSON, and clang-format 18 packages.
- Backend setup uses the built-in `setup-python` pip cache with both
  `backend/requirements.txt` and `backend/requirements-dev.txt` in the cache key.
  Each job still installs the development lockfile with `--require-hashes`.
- Frontend setup uses the built-in `setup-node` npm cache keyed by
  `frontend/package-lock.json`. `npm ci` installs the committed graph on both
  cache hits and misses; `node_modules` and test results are not cached.
- The Compose job builds the committed Dockerfiles and uses the smoke suite's
  temporary project, synthetic credentials, ephemeral ports, and cleanup.
  Container layer caching across workflow runs is not configured.
- Backend integration suites each create and drop a uniquely named database on the
  job's disposable PostgreSQL service. The explicit `REGISTRY_TEST_DATABASE_URL`
  uses synthetic CI credentials; no application environment or external server
  is used. The suite verifies up/down/up, duplicate device IDs, relationships,
  enabled-state ownership checks, and transactional, repeatable seeding.
  Telemetry checks cover identity conflicts and concurrent writes, UTC timestamps,
  nullable measurement time, database defaults/checks, and device/time indexes.
  HTTP tests also verify bearer credentials, mixed ownership/validation outcomes,
  commit failures, concurrent retries, and registry locks. Compose smoke invokes
  the simulator over HTTP and verifies telemetry persistence across stack restart.
  It also runs the eight shared QA edge cases and compares every persisted field
  with the catalog's accepted events, including original data after conflicts.

The backend PostgreSQL integration discovery includes
[`test_sprint1_qa.py`](../backend/tests/integration/test_sprint1_qa.py). Its ten
test names match the Sprint 1 QA matrix in the QA decision log:

| Test IDs | Contract checked |
| --- | --- |
| S1-QA-01..03 | Valid persistence, ten submissions with one row, and logged identity conflict without mutation. |
| S1-QA-04..06 | Ordered mixed outcomes, retry after a lost commit acknowledgement, and stable version/item rejection reasons. |
| S1-QA-07 | Null measurement time with an unsynchronised clock remains null. |
| S1-QA-08..09 | Older event times within a boot and from a prior boot remain in history without replacing current reading or advancing live alert state. |
| S1-QA-10 | PostgreSQL defines uniqueness on `(device_id, boot_id, sequence_number)`; a new boot can reuse a sequence number. |

The implemented current-reading and alert ordering rule uses event time (trusted
measurement time, otherwise gateway receipt time). The QA-08 and QA-09 checks
exercise replay with older event times; they do not establish a separate boot or
sequence cursor for readings whose event time is later.

Cache support follows the official [setup-python documentation](https://github.com/actions/setup-python#caching-packages-dependencies)
and [setup-node documentation](https://github.com/actions/setup-node#caching-global-packages-data).
Caches speed downloads; they never replace verification. Keep lockfiles updated
with manifest changes. CI needs no repository secrets, `.env` files, live backend,
or hardware. The workflow requests only `contents: read` token permissions.

## Reproduce a failure locally

Start from a clean checkout with Python 3.13 and Node.js 24.15+ (below 25). Follow the
[backend setup and validation commands](../backend/README.md#setup-and-validation)
to install locked dependencies and run Ruff and unittest.
The registry/telemetry integration command and PostgreSQL prerequisites are in the
[backend development checks](../backend/README.md#development-checks).
To run only the Sprint 1 QA matrix from `backend/`, use the same
`REGISTRY_TEST_DATABASE_URL` and run:

```sh
python -m unittest discover -s tests/integration -p test_sprint1_qa.py -v
```

In `frontend/`, run:

```sh
npm ci
npm run check
npm test
npm run build
```

The component suite mocks HTTP and controls timers. It checks loading, valid and
invalid readiness responses, proxy/network failure, retry recovery, timeout
cancellation, unmount cleanup, and StrictMode polling without a running server.

With Docker running, execute from the repository root:

```sh
docker compose config --quiet
python tests/compose_smoke.py
```

See [shared tests](../tests/README.md) for the smoke suite's outage, routing,
persistence, diagnostic logs, and cleanup behavior. Docker is required for this
job; unit-test success does not establish container integration success.
For native gateway commands, see [gateway build and test](../gateway/README.md#build-and-test).

## GitHub results

Open the commit or pull request's Checks tab, select the failed job, and inspect
the first failing step. The smoke suite prints bounded container logs on failure
and removes its own resources in `finally`. Job logs contain the test output.

To require verification before merging, repository rulesets or branch protection
must separately require `Backend lint and tests`, `Frontend checks, tests, and
build`, `Compose integration`, and `Gateway build and intake tests`.
Workflow files do not configure these repository settings, and
failed checks do not undo a push that already happened.
