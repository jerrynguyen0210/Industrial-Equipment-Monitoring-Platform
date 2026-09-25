# Simulator

The Python 3.13+ simulator uses only the standard library. `simulate.py` generates
deterministic temperature events for development and tests. `send_batch.py` sends
existing JSON fixtures. Both support direct `POST /api/v1/telemetry/batches`, check
ordered per-item results, and report accepted, duplicate, rejected and unconfirmed
counts as JSON. This API-only boundary bypasses MQTT and the native gateway;
hardware, gateway durability and load testing remain separate work.

## Generate a deterministic scenario

From the repository root, no backend or credentials are needed:

```powershell
.\.venv\Scripts\python.exe simulator/simulate.py --device-id device-demo-001 --run-id ramp-demo-001 --seed 7 --profile ramp --temperature 20 --step 0.5 --noise 0.1 --interval-ms 1000 --count 6 --reboot-every 3 --batch-size 2
```

The default `--mode generate` writes one compact JSON batch per stdout line
(NDJSON), and a JSON run summary to stderr. Each line is a complete v1 envelope;
the whole multi-line stream is **not** one API request. For a single fixture,
keep count at most 500 and set batch size equal to count:

```powershell
New-Item -ItemType Directory -Force test-results | Out-Null
.\.venv\Scripts\python.exe simulator/simulate.py --device-id device-demo-001 --run-id fixture-demo-001 --count 6 --batch-size 6 > test-results/simulator-batch.json
```

Generated output is ignored by Git. The unchanged file can be sent with
`send_batch.py --batch <path>`.

| Option | Default | Meaning |
| --- | --- | --- |
| `--device-id` | Required | Registered test device, 1-128 characters. |
| `--run-id` | Required | Scenario identity; choose a new value for each independent run. |
| `--boot-id` | Derived | Optional explicit initial boot ID; otherwise UUIDv5 from version, run and device. |
| `--seed` | `0` | Integer seed for a private random stream. |
| `--count` | `10` | Bounded workload, 1-1,000,000 events. |
| `--interval-ms` | `1000` | Positive integer sampling interval in milliseconds. |
| `--start-time` | `2026-01-01T00:00:00Z` | Fixed virtual start, with an explicit timezone, normalized to UTC. |
| `--reboot-every` | `0` | Reboot before every next group of N samples; zero disables reboot. |
| `--profile` | `constant` | `constant`, `ramp`, or `sine`. |
| `--temperature` | `25` | Constant value, ramp start, or sine centre, in Celsius. |
| `--step` | `0.1` | Ramp change in Celsius per sample, including negative slopes. |
| `--amplitude` | `5` | Nonnegative sine amplitude in Celsius. |
| `--period` | `60` | Sine period in samples, 1-1,000,000. |
| `--noise` | `0` | Nonnegative uniform noise half-width in Celsius. |
| `--batch-size` | `100` | 1-500 events per HTTP request or output line. |
| `--mode` | `generate` | Offline generation or direct `http`. |
| `--fast` | Off | Skip HTTP pacing, keeping all virtual timestamps unchanged. |
| `--api-base-url` | Environment/local | Overrides `API_BASE_URL`; fallback `http://127.0.0.1:8000/api`. |
| `--timeout` | `30` | HTTP timeout in seconds, greater than 0 and at most 300. |

For zero-based sample index `i`, constant is `temperature`, ramp is
`temperature + step*i`, and sine is `temperature + amplitude*sin(2*pi*i/period)`.
One seeded random draw adds noise in `[-noise, +noise)` on each sample; final
values are rounded to six decimal places. Nonfinite values and overflowing
timestamps/counters fail before sending. No physical sensor range is assumed.

The same simulator version, Python runtime, seed, configuration and start time
produce the same event bytes. Batch size and network timing do not affect events.
The temperature profile and noise stream continue across a reboot. Sequence and
uptime start at zero and increase within each boot; batch boundaries never reset
them. A reboot derives a new reproducible boot ID **before** resetting both.
For six events and `--reboot-every 3`, sequences are `0,1,2,0,1,2` across two IDs.

Use a new run ID for independent scenarios. Repeating the same inputs intentionally
replays the same identities. When overriding `--boot-id`, choose a new initial
boot ID as well for an independent run. Changing profile, seed, timing or count
while reusing identities can produce `identity_conflict`; it is not a fresh run.
Restarting the CLI starts a replay, not a persisted device session or automatic
reboot. Record all inputs before changing them.

Virtual `measured_at` is start plus sample index times interval. API-only mode
models a synchronized device and a gateway with zero receipt delay, so original
`gateway_received_at` equals measurement time. Both survive replay; no event
contains `backend_received_at`. The default historical start is for fixtures.
For current-time development, pass an explicit current `--start-time` and retain
it for retries. Historical events are not evidence of a live device.

## Send generated batches over HTTP

Provision the local gateway credential, migrate and seed using the setup below,
then run:

```powershell
.\.venv\Scripts\python.exe simulator/simulate.py --device-id device-demo-001 --run-id http-demo-001 --seed 7 --profile sine --temperature 25 --amplitude 5 --period 12 --interval-ms 250 --count 12 --reboot-every 6 --batch-size 3 --mode http
```

The API must know the device and authorize it for the credential's gateway.
HTTP mode uses the same `GATEWAY_API_KEY` process variable as the fixture sender.
It sends one batch at a time, after its last sample's scheduled wall-clock time;
the first sample is scheduled at zero. `--batch-size 1` sends individual samples
at the configured interval. Pacing uses monotonic deadlines, so HTTP duration
does not accumulate into the virtual schedule. Slow delivery is reported as
`max_schedule_lag_seconds`; this is not a throughput guarantee. `--fast` is useful
in tests and makes identical batches without waiting.

HTTP mode writes one final JSON summary to stdout with the configuration, version,
source revision (`-dirty` for local simulator edits), target, real duration,
actual sent throughput, outcome/rejection counts, and unsent/unconfirmed events.
Offline mode's `emitted` counts output events and its `unsent` counts events never
sent to the backend. Credentials are never recorded. For reproduction, preserve
the reported runtime, source revision and any local edits along with configuration.

The client never automatically retries. HTTP failures, incomplete confirmations,
or response loss leave the affected batch unconfirmed, stop later batches, and
exit `1`. Rejections are counted by reason, allow later batches to finish, and
also exit `1`; duplicates are successful confirmations. Ctrl+C reports cancellation,
unsent and possibly in-flight unconfirmed events, exiting `130`. Invalid arguments
exit `2`. Retry the exact original configuration: committed events become duplicates.
This is a bounded development simulator, without a durable delivery queue.

`events.py` exposes `Scenario`, `TemperatureProfile`, `generate_events`, `batches`
and `encode_batch` for tests. `simulate.run_scenario` accepts injected monotonic
clocks, sleeps, transport and output functions. Generation never consults wall time.

## Run the simulator-to-API slice

From the repository root in PowerShell, with Docker running and the repository
virtual environment available, generate a local prototype credential without
printing or committing it:

```powershell
$env:GATEWAY_API_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:GATEWAY_CREDENTIALS_JSON = @{ 'gateway-demo-001' = $env:GATEWAY_API_KEY } | ConvertTo-Json -Compress
docker compose up -d --build --wait
docker compose exec -T backend python -m alembic upgrade head
docker compose exec -T backend python -m app.seed
$env:API_BASE_URL = 'http://127.0.0.1:8000/api'
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/valid-batch.json --expect accepted
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/valid-batch.json --expect duplicate
.\.venv\Scripts\python.exe simulator/send_batch.py --batch simulator/fixtures/mixed-batch.json --expect 'accepted,rejected:invalid_unit,rejected:unknown_device'
```

For a fresh seeded database, the first call commits one row, replay reports
`duplicate`, and the mixed fixture commits one more row while rejecting the invalid
unit and unregistered device. Verify receipt-time ownership and persisted values:

```powershell
docker compose exec -T postgres psql -U iemp -d iemp -c "SELECT device_id, boot_id, sequence_number, value, measured_at, gateway_received_at, backend_received_at FROM telemetry WHERE boot_id = 'simulator-vertical-slice-v1' ORDER BY sequence_number;"
```

Use your configured PostgreSQL user/database if different from the local defaults.
Fixtures deliberately use fixed historical times and boot IDs for repeatable replay.
On later runs the valid entries are duplicates; use `--expect duplicate` and
`--expect 'duplicate,rejected:invalid_unit,rejected:unknown_device'`, respectively.
To test a new run, copy fixtures and change boot IDs consistently. No randomness,
clock substitution or automatic retries alter a submitted fixture.

`API_BASE_URL` and `GATEWAY_API_KEY` are read from the process environment;
`.env` is not automatically loaded. The key must match a registered, enabled
gateway in backend `GATEWAY_CREDENTIALS_JSON`. For native Uvicorn, export the same
map or use its documented explicit env-file loading. Restart the API after token
rotation/revocation. Keep tokens in ignored local configuration. HTTP redirects
are refused so credentials are sent only to the configured target.

The client sends original fixture bytes, preserving precise JSON numbers and
gateway receipt time. Missing, malformed, contradictory or misordered results are
unconfirmed and exit nonzero. HTTP/network failures also exit nonzero; retain the
fixture unchanged for retry. By default any rejection exits nonzero; `--expect`
allows explicit negative scenarios and requires the exact ordered outcome list.
This small sender accepts event-object fixtures; full malformed-envelope/item
coverage belongs to the backend contract tests. It is not a durable delivery queue.

## Verification

```powershell
# From the repository root, with backend development dependencies installed:
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml simulator
.\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml simulator
Push-Location simulator
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
.\.venv\Scripts\python.exe -u tests/compose_smoke.py
```

Unit/CLI tests cover known seeded values, all three profiles, byte-identical replay,
batch boundaries, reboot identities, pacing, cancellation, real loopback HTTP,
response loss, redirects and invalid configuration. The shared smoke suite creates
a fresh isolated stack, generates its own token, runs fixtures and a generated ramp
with two reboots, replays it, verifies PostgreSQL values/counters/receipt times, and
checks persistence across stack restart. CI runs both suites on every push/pull request.
See [Simulator Coding Conventions](CODING_CONVENTIONS.md) and the
[ingestion contract](../docs/telemetry-api-contract.md).
