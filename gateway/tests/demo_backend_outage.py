"""Run a native gateway through a backend outage against an isolated Compose stack."""

import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]


def wait_until(check, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.25)
    raise RuntimeError(f"timed out waiting for {description}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, default=ROOT / "gateway/build/gateway")
    parser.add_argument("--outage-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.outage_seconds < 60 or args.outage_seconds > 120:
        parser.error("--outage-seconds must be between 60 and 120")
    gateway_binary = args.gateway.resolve()
    if not gateway_binary.is_file():
        parser.error(f"gateway executable not found: {gateway_binary}")

    project = f"iemp-gateway-outage-{secrets.token_hex(5)}"
    boot_id = f"outage-{secrets.token_hex(8)}"
    token = secrets.token_urlsafe(24)
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        stable_backend_port = port_probe.getsockname()[1]
    environment = {
        **os.environ,
        "DATABASE_URL": "",
        "GATEWAY_CREDENTIALS_JSON": json.dumps({"gateway-demo-001": token}),
        "POSTGRES_DB": "iemp_gateway_demo",
        "POSTGRES_USER": "iemp_gateway_demo",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "BACKEND_BIND_ADDRESS": "127.0.0.1",
        "MQTT_BIND_ADDRESS": "127.0.0.1",
        "BACKEND_PORT": str(stable_backend_port),
        "MQTT_PORT": "0",
        "COMPOSE_PROFILES": "",
    }

    with tempfile.TemporaryDirectory(prefix="iemp-gateway-outage-") as temporary:
        directory = Path(temporary)
        auth_dir = directory / "mqtt-auth"
        subprocess.run(
            [sys.executable, ROOT / "infra/mosquitto/provision.py",
             "--output-dir", auth_dir],
            check=True, timeout=150,
        )
        environment["MQTT_AUTH_DIR"] = str(auth_dir)
        empty_env = directory / "empty.env"
        empty_env.touch()
        command = [
            "docker", "compose", "--project-name", project,
            "--env-file", str(empty_env), "--file", str(ROOT / "compose.yaml"),
        ]

        def compose(*args, timeout=180):
            result = subprocess.run(
                [*command, *args], cwd=ROOT, env=environment,
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Compose {args[0]} failed with exit {result.returncode}")
            return result.stdout.strip()

        def sql(query):
            return compose(
                "exec", "-T", "postgres", "sh", "-c",
                'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                '-v ON_ERROR_STOP=1 -Atc "$1"',
                "sh", query,
            )

        def publish(sequence):
            event = {
                "schema_version": 1,
                "device_id": "device-demo-001",
                "boot_id": boot_id,
                "sequence_number": sequence,
                "measured_at": None,
                "device_uptime_ms": sequence * 1000,
                "metric": "temperature",
                "value": 20.0 + sequence,
                "unit": "celsius",
                "quality": {"reading": "valid", "clock": "unsynchronised"},
            }
            compose(
                "exec", "-T", "--user", "0", "mosquitto", "sh", "-c",
                'exec mosquitto_pub -h 127.0.0.1 -u device-demo-001 '
                '-P "$(cat /mosquitto/config/auth/device-demo-001.password)" '
                '-q 1 -t equipment/device-demo-001/telemetry -m "$1"',
                "sh", json.dumps(event, separators=(",", ":")),
                timeout=20,
            )

        process = None
        log_file = None
        try:
            print(f"Starting isolated Compose project {project}", flush=True)
            compose("up", "-d", "--build", "--wait", "postgres", "mosquitto", "backend",
                    timeout=360)
            compose("exec", "-T", "backend", "python", "-m", "alembic", "upgrade", "head")
            compose("exec", "-T", "backend", "python", "-m", "app.db.seed")
            backend_port = int(compose("port", "backend", "8000").rsplit(":", 1)[1])
            mqtt_port = int(compose("port", "mosquitto", "1883").rsplit(":", 1)[1])
            config = directory / "gateway.env"
            queue_path = directory / "queue.sqlite3"
            config.write_text(
                f"MQTT_HOST=127.0.0.1\nMQTT_PORT={mqtt_port}\n"
                "MQTT_USERNAME=gateway-demo-001\n"
                f"MQTT_PASSWORD_FILE={auth_dir / 'gateway-demo-001.password'}\n"
                f"API_BASE_URL=http://127.0.0.1:{backend_port}/api\n"
                f"GATEWAY_API_KEY={token}\nQUEUE_DB_PATH={queue_path}\n"
            )
            config.chmod(0o600)
            log_path = directory / "gateway.log"
            log_file = log_path.open("w", encoding="utf-8")
            gateway_environment = environment.copy()
            for key in ("MQTT_HOST", "MQTT_PORT", "MQTT_USERNAME", "MQTT_PASSWORD_FILE",
                        "API_BASE_URL", "GATEWAY_API_KEY", "QUEUE_DB_PATH"):
                gateway_environment.pop(key, None)
            process = subprocess.Popen(
                [gateway_binary, "--config", config],
                stdout=log_file, stderr=subprocess.STDOUT,
                env=gateway_environment,
            )

            def gateway_alive():
                if process.poll() is not None:
                    raise RuntimeError(f"gateway exited with status {process.returncode}")
                return True

            def subscribed():
                gateway_alive()
                return '"event":"subscribed"' in log_path.read_text(encoding="utf-8")

            def queue_depth():
                gateway_alive()
                if not queue_path.exists():
                    return 0
                with sqlite3.connect(queue_path) as connection:
                    return connection.execute("SELECT COUNT(*) FROM intake_events").fetchone()[0]

            wait_until(subscribed, 20, "MQTT subscription")
            compose("stop", "backend")
            print(f"Backend stopped; holding outage for {args.outage_seconds} seconds", flush=True)
            for sequence in range(3):
                publish(sequence)
            wait_until(lambda: queue_depth() == 3, 10, "first three queued events")
            time.sleep(args.outage_seconds / 2)
            for sequence in range(3, 6):
                publish(sequence)
            wait_until(lambda: queue_depth() == 6, 10, "six queued events")
            print("Queue grew from 3 to 6 while the backend was stopped", flush=True)
            time.sleep(args.outage_seconds / 2)
            gateway_alive()
            compose("up", "-d", "--wait", "backend", timeout=180)
            print("Backend restarted; waiting for automatic queue drain", flush=True)
            wait_until(lambda: queue_depth() == 0, 90, "queue drain")
            rows = sql(
                "SELECT count(*), count(DISTINCT sequence_number) FROM telemetry "
                f"WHERE device_id='device-demo-001' AND boot_id='{boot_id}'"
            )
            if rows != "6|6":
                raise RuntimeError(f"expected six unique backend rows, got {rows}")
            if '"event":"retry_scheduled"' not in log_path.read_text(encoding="utf-8"):
                raise RuntimeError("gateway did not log retry scheduling")
            print("PASS: gateway stayed running; queue drained; backend has 6 unique rows", flush=True)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if log_file is not None:
                log_file.close()
            print(f"Removing isolated Compose project {project}", flush=True)
            compose("down", "--volumes", "--remove-orphans", "--timeout", "20", timeout=180)


if __name__ == "__main__":
    main()
