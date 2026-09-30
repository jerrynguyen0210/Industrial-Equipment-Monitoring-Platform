# version01 packaging validation

Validation date: `2026-09-30`  
Host: Linux ARM64, Python 3.13.5, Docker Engine 29.8.1, Docker Compose 5.5.1  
Source commit: `98461f28eca76bed4da7f85598a6aac3643d2ac0`

## Results

| Check | Result |
| --- | --- |
| Package secret/build-residue scan | Pass |
| Bash syntax and installer `--help` | Pass |
| `docker compose config --quiet` | Pass |
| Backend unit tests | Pass — 31 tests |
| Simulator unit tests with hash-locked dependency | Pass — 24 tests |
| Shared telemetry scenario tests | Pass — 7 tests |
| Isolated full-stack Docker smoke test | Pass — 10 checkpoints |

The full-stack test built the packaged backend and frontend, created an isolated
Compose project, and passed checks for packaged migrations and repeatable seed,
authenticated MQTT QoS 1 and ACL behavior, HTTP ingestion and replay, all eight
QA telemetry contract scenarios with exact database assertions, deterministic
reboot identities, health and frontend proxying, backend/database outage
recovery, and PostgreSQL/Mosquitto named-volume persistence. The test removed its
temporary project and volumes on completion.

The validation host's installed Docker Buildx plugin crashed with `SIGILL`, so
the smoke run used Docker's legacy builder by setting `DOCKER_BUILDKIT=0`. Both
packaged application images built successfully. This was a host plugin issue;
the normal customer procedure continues to require a working Docker installation
with the Compose build tooling supplied by Docker.

Physical ESP32 hardware, a DS18B20 probe, production security controls, backup
restore, and a real customer network were not part of this packaging validation.
They remain separate site acceptance activities and release gates.
