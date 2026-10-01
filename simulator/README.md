# Simulator

Python 3.13+ tool for deterministic temperature events. It can generate JSON,
publish device messages through MQTT, or send gateway-style HTTP batches.

## Generate data offline

```sh
python3 simulator/simulate.py \
  --device-id device-demo-001 --run-id ramp-demo-001 \
  --seed 7 --profile ramp --temperature 20 --step 0.5 \
  --interval-ms 1000 --count 6 --reboot-every 3 --batch-size 2
```

Generate mode writes one batch per output line and a summary to stderr. Use
`--profile constant`, `ramp`, or `sine`; run `--help` for all limits and options.

The same runtime, simulator version, run ID, seed, and options produce the same
event bytes. Reusing them intentionally replays the same identities. Changing
content while keeping identities produces `identity_conflict`. Use a new run ID
for an independent scenario.

## Publish through MQTT

1. Install the pinned MQTT client and start the broker:

   ```sh
   python3 -m pip install --require-hashes -r simulator/requirements.txt
   docker compose up -d --wait mosquitto
   export MQTT_PASSWORD_FILE=secrets/mosquitto/device-demo-001.password
   ```

2. Publish:

   ```sh
   python3 simulator/simulate.py \
     --device-id device-demo-001 --run-id mqtt-demo-001 \
     --profile ramp --count 5 --mode mqtt
   ```

MQTT mode sends one non-retained QoS 1 message per event. Its summary reports
broker acknowledgements only; run the native gateway to verify SQLite and backend
delivery. It has no durable queue or automatic retry.

## Send HTTP batches

1. Start, migrate, and seed the backend.
2. Export `API_BASE_URL` ending in `/api` and the matching `GATEWAY_API_KEY`.
3. Run:

   ```sh
   python3 simulator/simulate.py \
     --device-id device-demo-001 --run-id http-demo-001 \
     --profile sine --count 12 --batch-size 3 --mode http
   ```

HTTP mode checks every ordered result. Duplicates count as confirmed; rejections,
network failures, incomplete responses, and redirects exit nonzero. It does not
retry automatically. Retry with the exact original configuration so committed
events classify as duplicates.

## Run the simulator-to-API slice

```sh
export API_BASE_URL=http://127.0.0.1:8000/api
export GATEWAY_API_KEY="$(tr -d '\r\n' < secrets/gateway-demo-001.api-token)"
python3 simulator/send_batch.py \
  --batch simulator/fixtures/valid-batch.json --expect accepted
python3 simulator/send_batch.py \
  --batch simulator/fixtures/valid-batch.json --expect duplicate
unset GATEWAY_API_KEY API_BASE_URL
```

Fixtures preserve decimal text and receipt time. Keep a fixture unchanged when
retrying after an uncertain response.

## Verify

```sh
python -m ruff check --config backend/pyproject.toml simulator
python -m ruff format --check --config backend/pyproject.toml simulator
cd simulator
python -m unittest discover -s tests -v
```

See [Simulator Coding Conventions](CODING_CONVENTIONS.md) and the
[ingestion contract](../docs/telemetry-api-contract.md).
