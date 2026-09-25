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
| Backend lint and tests | Hash-locked dependencies, Ruff lint/format, backend and API simulator unit tests, and registry/telemetry/HTTP ingestion tests against PostgreSQL 17. Python lint also covers the simulator and Compose smoke script. | Python 3.13; 10 minutes. |
| Frontend checks, tests, and build | `npm ci`, TypeScript and Prettier checks, `npm test`, production build. | Node.js 24; 10 minutes. |
| Compose integration | Compose configuration validation and the isolated smoke suite against actual backend/frontend images, PostgreSQL, and Mosquitto. | Python 3.13 and Docker Compose; 20 minutes. |
| Gateway build (when implemented) | CMake Release configuration and C++17 compilation when `gateway/CMakeLists.txt` exists. | Runner CMake and C++ compiler; 10 minutes. |

Every install, lint, test, and build command must succeed. No check uses
`continue-on-error`, suppresses an error exit code, or retries a failed suite.
Frontend tests run once with `vitest run`; an empty suite fails. Steps after a
failure in the same job are skipped and the job stays failed. Other jobs continue.
Job timeouts also prevent a hung build or test from being reported as successful.

The gateway currently has no implementation. Its build steps are visibly skipped
and its job summary explains why. This is not proof of a working gateway. The
first CMake implementation activates the build automatically; add native system
dependencies and actual gateway tests in the same change.

## Repeatability and caches

- GitHub Actions are pinned to full commit SHAs. Runner OS and language major/minor
  versions are explicit; dependency versions are committed in lockfiles.
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
For native gateway commands, see [gateway setup](../gateway/README.md#setup-and-validation).

## GitHub results

Open the commit or pull request's Checks tab, select the failed job, and inspect
the first failing step. The smoke suite prints bounded container logs on failure
and removes its own resources in `finally`. Job logs contain the test output.

To require verification before merging, repository rulesets or branch protection
must separately require `Backend lint and tests`, `Frontend checks, tests, and
build`, and `Compose integration`. Require the gateway check once it is
implemented. Workflow files do not configure these repository settings, and
failed checks do not undo a push that already happened.
