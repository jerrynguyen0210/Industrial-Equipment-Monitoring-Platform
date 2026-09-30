#!/usr/bin/env python3
"""Autonomous, bounded setup agent for the IEMP lab platform."""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "Setup_Guide" / "install.sh"
LOG_DIRECTORY = Path(__file__).resolve().parent / "logs"
EXPECTED_SERVICES = {"backend", "frontend", "mosquitto", "postgres"}
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.3-codex"
MAX_TOOL_OUTPUT_CHARACTERS = 16_000


@dataclass(frozen=True)
class CommandResult:
    """A bounded representation of a child-process result."""

    command: tuple[str, ...]
    returncode: int
    output: str
    timed_out: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "output": self.output[-MAX_TOOL_OUTPUT_CHARACTERS:],
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class Settings:
    """Runtime configuration supplied by CLI flags and environment variables."""

    base_url: str
    api_key: str = field(repr=False)
    model: str
    max_turns: int
    command_timeout: int
    wait_timeout: int
    skip_host_install: bool
    test_api: bool


def positive_integer(value: str) -> int:
    """Parse a strictly positive CLI integer."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> Settings:
    """Load agent settings without accepting secrets on the command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the IEMP lab setup autonomously with OpenAI Codex and the "
            "Responses API."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI API base URL (default: https://api.openai.com/v1)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SETUP_AGENT_MODEL", DEFAULT_MODEL),
        help=f"OpenAI model ID (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-turns",
        type=positive_integer,
        default=int(os.environ.get("SETUP_AGENT_MAX_TURNS", "8")),
        help="maximum model turns (default: 8)",
    )
    parser.add_argument(
        "--command-timeout",
        type=positive_integer,
        default=int(os.environ.get("SETUP_AGENT_COMMAND_TIMEOUT", "3600")),
        help="maximum seconds for the installer (default: 3600)",
    )
    parser.add_argument(
        "--wait-timeout",
        type=positive_integer,
        default=int(os.environ.get("SETUP_AGENT_WAIT_TIMEOUT", "300")),
        help="Compose health-check timeout passed to the installer (default: 300)",
    )
    parser.add_argument(
        "--skip-host-install",
        action="store_true",
        default=os.environ.get("SETUP_AGENT_SKIP_HOST_INSTALL", "").lower()
        in {"1", "true", "yes"},
        help="require host prerequisites to exist instead of installing them",
    )
    parser.add_argument(
        "--test-api",
        action="store_true",
        help="test API authentication and Codex function calling without setup changes",
    )
    arguments = parser.parse_args(argv)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        parser.error("OPENAI_API_KEY is required")
    return Settings(
        base_url=arguments.base_url.rstrip("/"),
        api_key=api_key,
        model=arguments.model,
        max_turns=arguments.max_turns,
        command_timeout=arguments.command_timeout,
        wait_timeout=arguments.wait_timeout,
        skip_host_install=arguments.skip_host_install,
        test_api=arguments.test_api,
    )


def _tail(lines: deque[str]) -> str:
    output = "".join(lines)
    return output[-MAX_TOOL_OUTPUT_CHARACTERS:]


def _stop_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the isolated command process group after a timeout or interruption."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_command(
    command: Sequence[str],
    *,
    timeout: int,
    stream: bool = False,
    log_path: Path | None = None,
) -> CommandResult:
    """Run an allowlisted command and retain only a bounded output tail."""
    argv = tuple(str(part) for part in command)
    output_lines: deque[str] = deque(maxlen=500)
    started_at = time.monotonic()
    log_file = None
    process: subprocess.Popen[str] | None = None
    reader: threading.Thread | None = None

    def record(line: str) -> None:
        output_lines.append(line)
        if log_file is not None:
            log_file.write(line)
            log_file.flush()
        if stream:
            print(line, end="", flush=True)

    try:
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path.open("a", encoding="utf-8")
            log_file.write(f"\n$ {' '.join(argv)}\n")
            log_file.flush()
        process = subprocess.Popen(
            argv,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        assert process.stdout is not None
        output_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert process is not None and process.stdout is not None
            for line in process.stdout:
                output_queue.put(line)
            output_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        while True:
            elapsed = time.monotonic() - started_at
            if elapsed >= timeout:
                _stop_process_group(process)
                reader.join(timeout=1)
                while not output_queue.empty():
                    queued = output_queue.get_nowait()
                    if queued is not None:
                        record(queued)
                record(f"\nCommand timed out after {timeout} seconds.\n")
                return CommandResult(argv, 124, _tail(output_lines), timed_out=True)
            try:
                line = output_queue.get(timeout=min(0.2, timeout - elapsed))
            except queue.Empty:
                continue
            if line is None:
                return CommandResult(argv, process.wait(), _tail(output_lines))
            record(line)
    except FileNotFoundError:
        return CommandResult(argv, 127, f"Command not found: {argv[0]}\n")
    except OSError as error:
        return CommandResult(argv, 126, f"Unable to execute {argv[0]}: {error}\n")
    except BaseException:
        if process is not None:
            _stop_process_group(process)
        raise
    finally:
        if reader is not None:
            reader.join(timeout=1)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if log_file is not None:
            log_file.close()


def _read_local_setting(name: str, default: str) -> str:
    """Read a non-secret root setting with shell environment precedence."""
    if value := os.environ.get(name):
        return value
    env_path = REPO_ROOT / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return default
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip().strip("'\"") or default
    return default


def _http_json(url: str) -> dict[str, Any]:
    """Fetch a local JSON endpoint with a short, bounded timeout."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read(MAX_TOOL_OUTPUT_CHARACTERS).decode("utf-8")
            return {
                "ok": response.status == 200,
                "status": response.status,
                "body": json.loads(body),
            }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"ok": False, "error": str(error)}


def _parse_compose_ps(output: str) -> dict[str, dict[str, Any]]:
    """Accept both JSON-array and one-object-per-line Compose output."""
    stripped = output.strip()
    if not stripped:
        return {}
    try:
        decoded = json.loads(stripped)
        records = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        records = []
        for line in stripped.splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            records.extend(record if isinstance(record, list) else [record])
    return {
        str(record.get("Service")): record
        for record in records
        if isinstance(record, dict) and record.get("Service")
    }


class SetupTools:
    """The complete, intentionally narrow action surface exposed to the model."""

    def __init__(
        self,
        settings: Settings,
        *,
        command_runner: Callable[..., CommandResult] = run_command,
        http_getter: Callable[[str], dict[str, Any]] = _http_json,
    ) -> None:
        self.settings = settings
        self.command_runner = command_runner
        self.http_getter = http_getter
        self.setup_attempts = 0
        self.verified = False

    def inspect_environment(self) -> dict[str, Any]:
        """Inspect supported host prerequisites without changing the host."""
        commands = {
            "operating_system": ("uname", "-s"),
            "architecture": ("uname", "-m"),
            "python": ("python3", "--version"),
            "git": ("git", "--version"),
            "docker": ("docker", "--version"),
            "compose": ("docker", "compose", "version"),
            "docker_daemon": ("docker", "info", "--format", "{{.ServerVersion}}"),
        }
        checks = {
            name: self.command_runner(command, timeout=15).as_dict()
            for name, command in commands.items()
        }
        return {
            "ok": checks["operating_system"]["returncode"] == 0,
            "repository": str(REPO_ROOT),
            "installer_present": INSTALLER.is_file(),
            "checks": checks,
        }

    def run_platform_setup(self) -> dict[str, Any]:
        """Run the repository-owned, idempotent setup procedure."""
        if self.setup_attempts >= 2:
            return {
                "ok": False,
                "error": (
                    "The bounded retry limit of two installer attempts was reached."
                ),
            }
        self.setup_attempts += 1
        if not INSTALLER.is_file():
            return {"ok": False, "error": f"Installer is missing: {INSTALLER}"}
        command = [str(INSTALLER), "--wait-timeout", str(self.settings.wait_timeout)]
        if self.settings.skip_host_install:
            command.append("--skip-host-install")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = LOG_DIRECTORY / f"setup-{timestamp}.log"
        result = self.command_runner(
            command,
            timeout=self.settings.command_timeout,
            stream=True,
            log_path=log_path,
        )
        return {
            "ok": result.returncode == 0,
            "attempt": self.setup_attempts,
            "log_path": str(log_path),
            "result": result.as_dict(),
        }

    def verify_platform(self) -> dict[str, Any]:
        """Verify services, migrations, the demo seed, and both HTTP routes."""
        compose = self.command_runner(
            ("docker", "compose", "config", "--quiet"), timeout=30
        )
        services_result = self.command_runner(
            ("docker", "compose", "ps", "--format", "json"), timeout=30
        )
        services = _parse_compose_ps(services_result.output)
        service_checks: dict[str, Any] = {}
        for name in sorted(EXPECTED_SERVICES):
            record = services.get(name, {})
            state = str(record.get("State", "")).lower()
            health = str(record.get("Health", "")).lower()
            service_checks[name] = {
                "ok": state == "running" and health in {"", "healthy"},
                "state": state or "missing",
                "health": health or "not-reported",
            }

        migration = self.command_runner(
            (
                "docker",
                "compose",
                "exec",
                "-T",
                "backend",
                "python",
                "-m",
                "alembic",
                "current",
            ),
            timeout=60,
        )
        backend_port = _read_local_setting("BACKEND_PORT", "8000")
        frontend_port = _read_local_setting("FRONTEND_PORT", "8080")
        backend_health = self.http_getter(f"http://127.0.0.1:{backend_port}/ready")
        frontend_health = self.http_getter(
            f"http://127.0.0.1:{frontend_port}/api/health/ready"
        )
        devices = self.http_getter(f"http://127.0.0.1:{backend_port}/api/v1/devices")
        device_records = devices.get("body", {}).get("devices", [])
        seeded = any(
            isinstance(device, dict) and device.get("device_id") == "device-demo-001"
            for device in device_records
        )
        migration_ok = migration.returncode == 0 and "(head)" in migration.output
        ready_payload = {"status": "ready", "database": "ok"}
        backend_ok = (
            backend_health.get("ok") and backend_health.get("body") == ready_payload
        )
        frontend_ok = (
            frontend_health.get("ok") and frontend_health.get("body") == ready_payload
        )
        self.verified = bool(
            compose.returncode == 0
            and services_result.returncode == 0
            and all(check["ok"] for check in service_checks.values())
            and migration_ok
            and backend_ok
            and frontend_ok
            and devices.get("ok")
            and seeded
        )
        return {
            "ok": self.verified,
            "compose_config": compose.as_dict(),
            "services": service_checks,
            "migration": {
                "ok": migration_ok,
                "result": migration.as_dict(),
            },
            "backend_readiness": backend_health,
            "frontend_readiness": frontend_health,
            "demo_device_seeded": seeded,
        }

    def invoke(self, name: str) -> dict[str, Any]:
        """Dispatch only known no-argument tools."""
        tools: dict[str, Callable[[], dict[str, Any]]] = {
            "inspect_environment": self.inspect_environment,
            "run_platform_setup": self.run_platform_setup,
            "verify_platform": self.verify_platform,
        }
        tool = tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        try:
            return tool()
        except Exception as error:
            return {
                "ok": False,
                "error": f"{type(error).__name__}: {error}",
            }


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "inspect_environment",
        "description": (
            "Inspect Linux, Python, Git, Docker, Compose, and daemon availability "
            "without changing anything."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "run_platform_setup",
        "description": (
            "Run the repository's idempotent end-to-end installer. It may install "
            "host packages, provision local credentials, build services, migrate "
            "the database, seed the demo registry, and perform health checks."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "verify_platform",
        "description": (
            "Verify Compose services, database migration head, backend and "
            "frontend readiness, and the seeded demo device."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


AGENT_INSTRUCTIONS = """You are the IEMP Setup Agent. Complete the local lab setup
without asking the user questions. You have a deliberately bounded tool set.

Workflow:
1. Inspect the environment.
2. Verify the platform first, because setup is idempotent and may already be complete.
3. If verification fails, run the platform setup.
4. Verify again. Retry setup only when the returned evidence suggests a transient
   failure.
5. Report success only after verify_platform returns ok=true. Otherwise report the exact
   unresolved blocker and the relevant safe error output.

Never invent command results, never claim unverified success, never request or reveal
credentials, and do not tell the user to run steps that an available tool can perform.
Keep the final report concise. Do not expose hidden reasoning.
"""


def _safe_api_error(error: Exception, api_key: str) -> str:
    """Return an SDK error without ever echoing the configured API key."""
    return str(error).replace(api_key, "[REDACTED]")


def _create_openai_client(settings: Settings) -> Any:
    """Create the official SDK client lazily so unit tests need no dependency."""
    from openai import OpenAI

    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=180.0,
        max_retries=1,
    )


def test_api_connection(settings: Settings) -> int:
    """Test the API key, selected Codex model, and Responses function calling."""
    try:
        client = _create_openai_client(settings)
        response = client.responses.create(
            model=settings.model,
            instructions=(
                "This is a connectivity test. Call confirm_setup_agent_api exactly "
                "once and do not call any other tool."
            ),
            input="Confirm that the setup agent can use function calling.",
            reasoning={"effort": "low"},
            tools=[
                {
                    "type": "function",
                    "name": "confirm_setup_agent_api",
                    "description": "Confirm API and function-calling connectivity.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            ],
            tool_choice={"type": "function", "name": "confirm_setup_agent_api"},
        )
    except ImportError:
        print(
            "The OpenAI Python SDK is not installed. Run agents/setup_agent/run.sh.",
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        print(
            "OpenAI Codex API test failed: " + _safe_api_error(error, settings.api_key),
            file=sys.stderr,
        )
        return 2

    called = any(
        item.type == "function_call" and item.name == "confirm_setup_agent_api"
        for item in response.output
    )
    if not called:
        print(
            "OpenAI Codex responded, but the function-calling test did not pass.",
            file=sys.stderr,
        )
        return 1
    print(f"OpenAI Codex API test passed with model {settings.model}.")
    return 0


def run_agent(settings: Settings, tools: SetupTools) -> int:
    """Run the Responses tool loop, enforcing application-level verification."""
    try:
        client = _create_openai_client(settings)
    except ImportError:
        print(
            "The OpenAI Python SDK is not installed. Run agents/setup_agent/run.sh.",
            file=sys.stderr,
        )
        return 2

    input_items: list[Any] = [
        {
            "role": "user",
            "content": (
                "Set up this Industrial Equipment Monitoring Platform end to end and "
                "independently. Begin now and finish only after objective verification."
            ),
        },
    ]

    try:
        for _ in range(settings.max_turns):
            response = client.responses.create(
                model=settings.model,
                instructions=AGENT_INSTRUCTIONS,
                input=input_items,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                reasoning={"effort": "medium"},
            )
            input_items += response.output
            function_calls = [
                item for item in response.output if item.type == "function_call"
            ]
            if function_calls:
                for tool_call in function_calls:
                    print(f"[setup-agent] {tool_call.name}", flush=True)
                    result = tools.invoke(tool_call.name)
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": json.dumps(result, ensure_ascii=True),
                        }
                    )
                continue

            if tools.verified:
                print(
                    response.output_text or "Setup completed and verification passed."
                )
                return 0
            input_items.append(
                {
                    "role": "user",
                    "content": (
                        "The application has not recorded a successful verification. "
                        "Continue using the available tools; do not claim completion."
                    ),
                }
            )
    except Exception as error:
        print(
            f"Setup agent could not use model {settings.model!r} at "
            f"{settings.base_url}: {_safe_api_error(error, settings.api_key)}",
            file=sys.stderr,
        )
        return 2

    final_verification = tools.verify_platform()
    if final_verification["ok"]:
        print("Setup completed and verification passed.")
        return 0
    print(
        "Setup agent exhausted its bounded model turns before verification passed.\n"
        + json.dumps(final_verification, indent=2),
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    settings = parse_args(argv)
    if settings.test_api:
        return test_api_connection(settings)
    return run_agent(settings, SetupTools(settings))


if __name__ == "__main__":
    raise SystemExit(main())
