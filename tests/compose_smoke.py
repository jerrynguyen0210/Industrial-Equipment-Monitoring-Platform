"""Exercise an isolated Compose stack; requires Python 3.13+ and Docker Compose."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from telemetry_scenarios import load_scenarios

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("Docker is required. Install/start Docker and retry.")

    # Never use the developer's project, .env, fixed ports, or named volumes.
    project = f"iemp-smoke-{secrets.token_hex(6)}"
    gateway_token = secrets.token_urlsafe(24)
    environment = {
        **os.environ,
        "DATABASE_URL": "",
        "GATEWAY_CREDENTIALS_JSON": json.dumps({"gateway-demo-001": gateway_token}),
        "VITE_API_BASE_URL": "/api",
        "POSTGRES_DB": "iemp_smoke",
        "POSTGRES_USER": "iemp_smoke",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "FRONTEND_BIND_ADDRESS": "127.0.0.1",
        "BACKEND_BIND_ADDRESS": "127.0.0.1",
        "MQTT_BIND_ADDRESS": "127.0.0.1",
        "FRONTEND_PORT": "0",
        "BACKEND_PORT": "0",
        "MQTT_PORT": "0",
        "COMPOSE_PROFILES": "",
    }

    with tempfile.TemporaryDirectory(prefix="iemp-smoke-") as directory:
        empty_env = Path(directory) / "empty.env"
        empty_env.touch()
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(empty_env),
            "--file",
            str(ROOT / "compose.yaml"),
        ]

        def compose(*args: str, timeout: int = 180) -> str:
            result = subprocess.run(
                [*command, *args],
                cwd=ROOT,
                env=environment,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
            )
            return result.stdout.strip()

        def published_port(service: str, port: int) -> int:
            return int(compose("port", service, str(port)).rsplit(":", 1)[1])

        def url(service: str, port: int, path: str) -> str:
            return f"http://127.0.0.1:{published_port(service, port)}{path}"

        def request(address: str) -> tuple[int, str]:
            # Do not route localhost smoke checks through a host HTTP proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open(address, timeout=8) as response:
                    return response.status, response.read().decode()
            except urllib.error.HTTPError as error:
                return error.code, error.read().decode()
            except urllib.error.URLError as error:
                # The container may be healthy while Docker is still wiring the
                # published host port after a down/up cycle.
                raise ConnectionError(
                    f"HTTP endpoint not accepting connections: {address}"
                ) from error

        def wait_ready(address: str, timeout: float = 45) -> None:
            deadline = time.monotonic() + timeout
            last_result = "No response"

            while time.monotonic() < deadline:
                try:
                    status, body = request(address)
                    last_result = f"HTTP {status}: {body[:200]}"
                    if status == 200 and json.loads(body) == {
                        "status": "ready",
                        "database": "ok",
                    }:
                        return
                except (ConnectionError, OSError, ValueError) as error:
                    last_result = type(error).__name__

                time.sleep(0.5)

            raise AssertionError(f"Readiness timed out: {last_result}")

        def sql(query: str) -> str:
            return compose(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                '-v ON_ERROR_STOP=1 -Atc "$1"',
                "sh",
                query,
            )

        def publish(topic: str, value: str) -> None:
            compose(
                "exec",
                "-T",
                "mosquitto",
                "mosquitto_pub",
                "-h",
                "127.0.0.1",
                "-t",
                topic,
                "-m",
                value,
                "-r",
                "-q",
                "1",
            )

        def retained(topic: str) -> str:
            return compose(
                "exec",
                "-T",
                "mosquitto",
                "mosquitto_sub",
                "-h",
                "127.0.0.1",
                "-t",
                topic,
                "-C",
                "1",
                "-W",
                "5",
            )

        def require(condition: bool, message: str) -> None:
            if not condition:
                raise AssertionError(message)

        def show_health_checks() -> None:
            for service in ("postgres", "mosquitto", "backend", "frontend"):
                try:
                    container_id = compose("ps", "--all", "-q", service)
                    if not container_id:
                        continue
                    result = subprocess.run(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{json .State.Health}}",
                            container_id,
                        ],
                        check=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        capture_output=True,
                        timeout=10,
                    )
                    health = json.loads(result.stdout)
                    if health:
                        print(f"{service} health: {health['Status']}")
                        for check in health.get("Log", [])[-3:]:
                            output = check.get("Output", "").strip()
                            print(f"  exit {check['ExitCode']}: {output[:1000]}")
                except (subprocess.SubprocessError, ValueError, KeyError) as error:
                    print(f"Could not inspect {service} health: {type(error).__name__}")

        try:
            print(f"Starting isolated project {project}", flush=True)
            compose("config", "--quiet")
            compose("up", "--build", "--wait", "--wait-timeout", "120", timeout=600)
            frontend = url("frontend", 8080, "/")
            ready = url("frontend", 8080, "/api/health/ready")
            backend_ready = url("backend", 8000, "/ready")
            live = url("backend", 8000, "/health")
            status, page = request(frontend)
            require(status == 200, "Frontend failed to serve HTML")
            require(
                "Industrial Equipment Monitoring Platform" in page, "Wrong frontend"
            )
            wait_ready(ready)
            wait_ready(backend_ready)
            status, body = request(live)
            require(
                status == 200 and json.loads(body) == {"status": "ok"},
                "Backend liveness contract failed",
            )
            with socket.create_connection(
                ("127.0.0.1", published_port("mosquitto", 1883)), timeout=5
            ):
                pass
            marker = secrets.token_hex(12)
            topic = "iemp/smoke/persistence"
            compose(
                "exec", "-T", "backend", "python", "-m", "alembic", "upgrade", "head"
            )
            for _ in range(2):
                compose("exec", "-T", "backend", "python", "-m", "app.seed")
            registry_query = (
                "SELECT d.device_id FROM devices d "
                "JOIN gateways g ON g.gateway_id = d.gateway_id "
                "JOIN sites s ON s.site_id = g.site_id "
                "WHERE d.device_id = 'device-demo-001' "
                "AND g.gateway_id = 'gateway-demo-001' "
                "AND s.site_id = 'site-demo-001' "
                "AND d.enabled AND g.enabled AND s.enabled"
            )
            require(sql(registry_query) == "device-demo-001", "Registry seed failed")
            print("PASS: packaged migration and repeatable registry seed", flush=True)
            simulator_environment = environment | {
                "API_BASE_URL": url("backend", 8000, "/api"),
                "GATEWAY_API_KEY": gateway_token,
            }
            for fixture, expected in (
                ("valid-batch.json", "accepted"),
                ("valid-batch.json", "duplicate"),
                (
                    "mixed-batch.json",
                    "accepted,rejected:invalid_unit,rejected:unknown_device",
                ),
            ):
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "simulator/send_batch.py"),
                        "--batch",
                        str(ROOT / "simulator/fixtures" / fixture),
                        "--expect",
                        expected,
                    ],
                    env=simulator_environment,
                    check=True,
                    timeout=40,
                )
            telemetry_query = (
                "SELECT count(*) FROM telemetry "
                "WHERE device_id = 'device-demo-001' "
                "AND boot_id = 'simulator-vertical-slice-v1' "
                "AND backend_received_at IS NOT NULL"
            )
            require(sql(telemetry_query) == "2", "Simulator telemetry did not persist")
            print(
                "PASS: simulator HTTP ingestion, retries, mixed items and persistence",
                flush=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/telemetry_scenarios.py"),
                    "--run-id",
                    "compose-qa",
                    "--output-dir",
                    directory,
                ],
                env=simulator_environment,
                check=True,
                timeout=150,
            )
            # Compare every field of every accepted identity, not only row counts.
            # Expectations come from the fixture catalog, never backend validation.
            expected_qa_rows = []
            qa_scenarios = load_scenarios("compose-qa")
            for scenario in qa_scenarios:
                for step in scenario["steps"]:
                    for item, outcome in zip(
                        step["batch"]["events"], step["expected"], strict=True
                    ):
                        if outcome == "accepted":
                            row = item | {"schema_version": 1}
                            for field in ("measured_at", "gateway_received_at"):
                                if row[field] is not None:
                                    row[field] = datetime.fromisoformat(
                                        row[field]
                                    ).isoformat()
                            expected_qa_rows.append(row)
            qa_query = (
                "SELECT COALESCE(jsonb_agg(to_jsonb(t) - 'id' - 'backend_received_at' "
                "ORDER BY boot_id, sequence_number), '[]'::jsonb) FROM telemetry t "
                "WHERE boot_id LIKE 'qa-compose-qa-%'"
            )
            require(
                len(expected_qa_rows)
                == sum(case["expected_rows"] for case in qa_scenarios)
                and json.loads(sql(qa_query))
                == sorted(
                    expected_qa_rows,
                    key=lambda row: (row["boot_id"], row["sequence_number"]),
                ),
                "QA rows differ: rejected insert, changed original, or missing data",
            )
            qa_snapshot_query = (
                "SELECT jsonb_agg(to_jsonb(t) ORDER BY boot_id, sequence_number) "
                "FROM telemetry t WHERE boot_id LIKE 'qa-compose-qa-%'"
            )
            qa_snapshot = sql(qa_snapshot_query)
            require(
                all(
                    row["backend_received_at"] is not None
                    for row in json.loads(qa_snapshot)
                ),
                "QA accepted event has no server receipt time",
            )
            print(
                "PASS: eight QA contract edge cases and exact persisted rows",
                flush=True,
            )
            generated_query = (
                "SELECT json_agg(json_build_array(sequence_number, device_uptime_ms, "
                "value) ORDER BY measured_at), count(DISTINCT boot_id) "
                "FROM telemetry WHERE device_id = 'device-demo-001' "
                "AND measured_at >= '2026-01-01T00:00:00Z' "
                "AND measured_at < '2026-01-01T00:00:05Z' "
                "AND backend_received_at IS NOT NULL "
                "AND gateway_received_at = measured_at"
            )
            for outcome in ("accepted", "duplicate"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "simulator/simulate.py"),
                        "--device-id",
                        "device-demo-001",
                        "--run-id",
                        "compose-generated-v1",
                        "--seed",
                        "7",
                        "--count",
                        "5",
                        "--batch-size",
                        "2",
                        "--reboot-every",
                        "2",
                        "--profile",
                        "ramp",
                        "--temperature",
                        "20",
                        "--step",
                        "0.5",
                        "--mode",
                        "http",
                        "--fast",
                    ],
                    env=simulator_environment,
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=40,
                )
                summary = json.loads(result.stdout)
                require(
                    summary["counts"][outcome] == 5
                    and summary["unconfirmed"] == summary["unsent"] == 0,
                    f"Generated scenario did not report five {outcome} events",
                )
            generated_rows, boot_count = sql(generated_query).rsplit("|", 1)
            require(
                json.loads(generated_rows)
                == [
                    [0, 0, 20],
                    [1, 1000, 20.5],
                    [0, 0, 21],
                    [1, 1000, 21.5],
                    [0, 0, 22],
                ]
                and boot_count == "3",
                "Generated values, reboot identities or counters did not persist",
            )
            print(
                "PASS: deterministic generated scenario, reboots and replay", flush=True
            )
            sql("CREATE TABLE compose_smoke (value text NOT NULL)")
            sql(f"INSERT INTO compose_smoke VALUES ('{marker}')")
            publish(topic, marker)
            require(retained(topic) == marker, "MQTT publish/subscribe failed")
            print("PASS: health checks, frontend proxy, SQL, and MQTT", flush=True)

            compose("stop", "backend")
            publish(topic, marker + "-outage")
            require(retained(topic) == marker + "-outage", "MQTT depends on backend")
            require(request(frontend)[0] == 200, "Frontend stopped with backend")
            require(request(ready)[0] == 502, "Proxy concealed a backend outage")
            compose("up", "--wait", "--wait-timeout", "60", "backend")
            backend_ready = url("backend", 8000, "/ready")
            live = url("backend", 8000, "/health")
            wait_ready(ready)
            print("PASS: MQTT and frontend survive backend outage", flush=True)

            compose("stop", "postgres")
            status, body = request(live)
            require(
                status == 200 and json.loads(body) == {"status": "ok"},
                "Database outage broke API liveness",
            )
            for address in (backend_ready, ready):
                status, body = request(address)
                require(
                    status == 503
                    and json.loads(body)
                    == {"status": "unavailable", "database": "unavailable"},
                    f"Readiness concealed a database outage at {address}",
                )
            compose("up", "--wait", "--wait-timeout", "60", "postgres")
            wait_ready(backend_ready)
            wait_ready(ready)
            print("PASS: database outage and readiness recovery", flush=True)

            compose("up", "-d", "--no-deps", "--force-recreate", "backend")
            wait_ready(ready)
            print("PASS: frontend proxy recovers after backend recreation", flush=True)

            # Graceful down flushes Mosquitto persistence; volumes must survive.
            compose("down", "--timeout", "20")
            compose("up", "--wait", "--wait-timeout", "120")
            wait_ready(url("frontend", 8080, "/api/health/ready"))
            require(sql("SELECT value FROM compose_smoke") == marker, "SQL data lost")
            require(sql(registry_query) == "device-demo-001", "Registry data lost")
            require(sql(telemetry_query) == "2", "Telemetry data lost")
            require(
                sql(qa_snapshot_query) == qa_snapshot,
                "QA telemetry changed after restart",
            )
            require(
                sql(generated_query) == generated_rows + "|" + boot_count,
                "Generated simulator telemetry lost",
            )
            require(retained(topic) == marker + "-outage", "MQTT retained data lost")
            print("PASS: both named volumes survive down/up", flush=True)
        except Exception as error:
            # This stack has only synthetic data; never print its environment.
            if isinstance(error, subprocess.CalledProcessError):
                print(error.stdout or "")
                print(error.stderr or "")
            show_health_checks()
            try:
                print(compose("logs", "--no-color", "--tail", "60"))
            except subprocess.SubprocessError:
                print("Could not collect container logs.")
            raise
        finally:
            try:
                print(compose("ps", "--all"))
            finally:
                print(f"Removing isolated project {project} and its test volumes")
                compose("down", "--volumes", "--remove-orphans", "--timeout", "20")


if __name__ == "__main__":
    main()
