"""Unit tests for the bounded setup-agent tools."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "setup_agent.py"
SPEC = importlib.util.spec_from_file_location("iemp_setup_agent", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
setup_agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = setup_agent
SPEC.loader.exec_module(setup_agent)


def settings(**overrides: Any) -> Any:
    values = {
        "base_url": "https://api.openai.com/v1",
        "api_key": "test-api-key",
        "model": "gpt-5.3-codex",
        "max_turns": 8,
        "command_timeout": 3600,
        "wait_timeout": 300,
        "skip_host_install": False,
        "test_api": False,
    }
    values.update(overrides)
    return setup_agent.Settings(**values)


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        command: Sequence[str],
        *,
        timeout: int,
        stream: bool = False,
        log_path: Path | None = None,
    ) -> Any:
        del timeout, stream, log_path
        argv = tuple(str(part) for part in command)
        self.calls.append(argv)
        returncode, output = self.responses.get(argv, (0, ""))
        return setup_agent.CommandResult(argv, returncode, output)


class SetupToolsTests(unittest.TestCase):
    def test_api_key_is_hidden_from_settings_representation(self) -> None:
        configured = settings(api_key="do-not-print-this-key")

        self.assertNotIn("do-not-print-this-key", repr(configured))

    def test_arguments_require_openai_api_key(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            setup_agent.parse_args([])

        self.assertEqual(raised.exception.code, 2)

    def test_arguments_default_to_codex_and_responses_api(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True):
            parsed = setup_agent.parse_args(["--test-api"])

        self.assertEqual(parsed.model, "gpt-5.3-codex")
        self.assertEqual(parsed.base_url, "https://api.openai.com/v1")
        self.assertEqual(parsed.api_key, "secret")
        self.assertTrue(parsed.test_api)

    def test_api_smoke_test_uses_codex_responses_function_calling(self) -> None:
        calls: list[dict[str, Any]] = []

        class FakeResponses:
            def create(self, **kwargs: Any) -> Any:
                calls.append(kwargs)
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="confirm_setup_agent_api",
                        )
                    ]
                )

        client = SimpleNamespace(responses=FakeResponses())
        stdout = io.StringIO()
        with (
            patch.object(setup_agent, "_create_openai_client", return_value=client),
            contextlib.redirect_stdout(stdout),
        ):
            returncode = setup_agent.test_api_connection(settings())

        self.assertEqual(returncode, 0)
        self.assertEqual(calls[0]["model"], "gpt-5.3-codex")
        self.assertEqual(calls[0]["reasoning"], {"effort": "low"})
        self.assertEqual(calls[0]["tools"][0]["type"], "function")
        self.assertIn("passed", stdout.getvalue())

    def test_agent_uses_responses_tool_loop_until_verified(self) -> None:
        responses = iter(
            [
                SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="inspect_environment",
                            call_id="call-inspect",
                        )
                    ],
                    output_text="",
                ),
                SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="verify_platform",
                            call_id="call-verify",
                        )
                    ],
                    output_text="",
                ),
                SimpleNamespace(output=[], output_text="Setup verified."),
            ]
        )
        requests: list[dict[str, Any]] = []

        class FakeResponses:
            def create(self, **kwargs: Any) -> Any:
                request = dict(kwargs)
                request["input"] = list(kwargs["input"])
                requests.append(request)
                return next(responses)

        class FakeTools:
            def __init__(self) -> None:
                self.verified = False
                self.calls: list[str] = []

            def invoke(self, name: str) -> dict[str, Any]:
                self.calls.append(name)
                if name == "verify_platform":
                    self.verified = True
                return {"ok": True}

        client = SimpleNamespace(responses=FakeResponses())
        tools = FakeTools()
        stdout = io.StringIO()
        with (
            patch.object(setup_agent, "_create_openai_client", return_value=client),
            contextlib.redirect_stdout(stdout),
        ):
            returncode = setup_agent.run_agent(settings(max_turns=3), tools)

        self.assertEqual(returncode, 0)
        self.assertEqual(tools.calls, ["inspect_environment", "verify_platform"])
        self.assertEqual(requests[0]["model"], "gpt-5.3-codex")
        self.assertEqual(requests[0]["reasoning"], {"effort": "medium"})
        self.assertTrue(
            any(
                item.get("type") == "function_call_output"
                and item.get("call_id") == "call-inspect"
                for item in requests[1]["input"]
                if isinstance(item, dict)
            )
        )
        self.assertIn("Setup verified.", stdout.getvalue())

    def test_command_timeout_preserves_output_and_stops_process(self) -> None:
        result = setup_agent.run_command(
            (
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(5)",
            ),
            timeout=1,
        )

        self.assertEqual(result.returncode, 124)
        self.assertTrue(result.timed_out)
        self.assertIn("started", result.output)
        self.assertIn("timed out", result.output)

    def test_installer_uses_repository_script_and_configured_options(self) -> None:
        runner = FakeRunner({})
        tools = setup_agent.SetupTools(
            settings(skip_host_install=True, wait_timeout=456), command_runner=runner
        )

        result = tools.run_platform_setup()

        self.assertTrue(result["ok"])
        self.assertEqual(
            runner.calls,
            [
                (
                    str(setup_agent.INSTALLER),
                    "--wait-timeout",
                    "456",
                    "--skip-host-install",
                )
            ],
        )

    def test_installer_stops_after_two_attempts(self) -> None:
        runner = FakeRunner({})
        tools = setup_agent.SetupTools(settings(), command_runner=runner)

        self.assertTrue(tools.run_platform_setup()["ok"])
        self.assertTrue(tools.run_platform_setup()["ok"])
        self.assertFalse(tools.run_platform_setup()["ok"])
        self.assertEqual(len(runner.calls), 2)

    def test_verification_requires_services_migration_health_and_seed(self) -> None:
        service_records = [
            {"Service": name, "State": "running", "Health": "healthy"}
            for name in sorted(setup_agent.EXPECTED_SERVICES)
        ]
        responses = {
            ("docker", "compose", "ps", "--format", "json"): (
                0,
                json.dumps(service_records),
            ),
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
            ): (0, "0004_temperature_alerts (head)\n"),
        }
        runner = FakeRunner(responses)

        def http_getter(url: str) -> dict[str, Any]:
            if url.endswith("/api/v1/devices"):
                return {
                    "ok": True,
                    "status": 200,
                    "body": {"devices": [{"device_id": "device-demo-001"}]},
                }
            return {
                "ok": True,
                "status": 200,
                "body": {"status": "ready", "database": "ok"},
            }

        tools = setup_agent.SetupTools(
            settings(), command_runner=runner, http_getter=http_getter
        )

        result = tools.verify_platform()

        self.assertTrue(result["ok"])
        self.assertTrue(tools.verified)

    def test_verification_fails_when_a_service_is_unhealthy(self) -> None:
        service_records = [
            {
                "Service": name,
                "State": "running",
                "Health": "unhealthy" if name == "mosquitto" else "healthy",
            }
            for name in sorted(setup_agent.EXPECTED_SERVICES)
        ]
        runner = FakeRunner(
            {
                ("docker", "compose", "ps", "--format", "json"): (
                    0,
                    "\n".join(json.dumps(record) for record in service_records),
                ),
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
                ): (0, "0004_temperature_alerts (head)\n"),
            }
        )

        def http_getter(url: str) -> dict[str, Any]:
            if url.endswith("/api/v1/devices"):
                return {
                    "ok": True,
                    "body": {"devices": [{"device_id": "device-demo-001"}]},
                }
            return {"ok": True, "body": {"status": "ready", "database": "ok"}}

        tools = setup_agent.SetupTools(
            settings(), command_runner=runner, http_getter=http_getter
        )

        result = tools.verify_platform()

        self.assertFalse(result["ok"])
        self.assertFalse(result["services"]["mosquitto"]["ok"])


if __name__ == "__main__":
    unittest.main()
