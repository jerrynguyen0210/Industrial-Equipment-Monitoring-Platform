"""Exercise an isolated Compose stack; requires Python 3.13+ and Docker Compose."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("Docker is required. Install/start Docker and retry.")

    # Never use the developer's project, .env, fixed ports, or named volumes.
    project = f"iemp-smoke-{secrets.token_hex(6)}"
    environment = {
        **os.environ,
        "DATABASE_URL": "",
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
