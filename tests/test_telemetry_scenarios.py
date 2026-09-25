"""CLI and fixture checks; real backend/storage assertions run in Compose smoke."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from telemetry_scenarios import ROOT, encode_batch, export_scenarios, load_scenarios


class FixtureTests(unittest.TestCase):
    def test_scenarios_are_independent_repeatable_and_have_explicit_expectations(self):
        scenarios = load_scenarios("test-run")
        self.assertEqual(scenarios, load_scenarios("test-run"))
        self.assertEqual(len(scenarios), 8)
        self.assertEqual(sum(case["expected_rows"] for case in scenarios), 9)
        boot_ids = set()
        for case in scenarios:
            for step in case["steps"]:
                self.assertEqual(len(step["batch"]["events"]), len(step["expected"]))
                boot_ids.update(event["boot_id"] for event in step["batch"]["events"])
            self.assertEqual(load_scenarios("test-run", names=[case["name"]]), [case])
        self.assertEqual(len(boot_ids), 8)
        other_boots = {
            event["boot_id"]
            for case in load_scenarios("other-run")
            for step in case["steps"]
            for event in step["batch"]["events"]
        }
        self.assertTrue(boot_ids.isdisjoint(other_boots))

    def test_retries_conflicts_historical_and_sequence_payloads_are_intentional(self):
        cases = {case["name"]: case["steps"] for case in load_scenarios("fixed")}
        self.assertEqual(
            encode_batch(cases["duplicate"][0]["batch"]),
            encode_batch(cases["duplicate"][1]["batch"]),
        )
        original, conflict, retry = [
            step["batch"]["events"][0] for step in cases["identity-conflict"]
        ]
        self.assertEqual(original, retry)
        self.assertEqual(conflict, original | {"value": 99})
        self.assertEqual(
            cases["stale-timestamp"][0]["batch"]["events"][0]["measured_at"],
            "2000-01-01T00:00:00Z",
        )
        self.assertEqual(
            [
                event["sequence_number"]
                for step in cases["out-of-order-sequence"]
                for event in step["batch"]["events"]
            ],
            [12, 10, 11],
        )

    def test_exported_requests_are_exact_and_existing_evidence_is_not_overwritten(self):
        cases = load_scenarios("fixed", device_id="custom-device")
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "fixed"
            export_scenarios(cases, directory, "fixed")
            manifest = json.loads((directory / "expected.json").read_bytes())
            for case, exported in zip(cases, manifest["scenarios"], strict=True):
                for step, export in zip(case["steps"], exported["steps"], strict=True):
                    self.assertEqual(
                        (directory / export["fixture"]).read_bytes(),
                        encode_batch(step["batch"]),
                    )
                    self.assertEqual(export["expected"], step["expected"])
                    self.assertEqual(export["http_status"], 200)
            with self.assertRaises(FileExistsError):
                export_scenarios(cases, directory, "fixed")
        unknown = cases[4]["steps"][0]["batch"]["events"][0]["device_id"]
        self.assertEqual(unknown, "qa-unknown-fixed")
        self.assertEqual(
            cases[0]["steps"][0]["batch"]["events"][0]["device_id"], "custom-device"
        )

    def test_invalid_names_and_identity_namespaces_fail_before_requests(self):
        for run_id in ("../escape", "", "x" * 49):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                load_scenarios(run_id)
        with self.assertRaises(ValueError):
            load_scenarios("fixed", names=["typo"])
        with self.assertRaises(ValueError):
            load_scenarios("fixed", device_id="qa-unknown-fixed")


class RunnerTests(unittest.TestCase):
    def run_cli(self, *args, url="http://127.0.0.1:1/api"):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/telemetry_scenarios.py"),
                "--run-id",
                "cli-test",
                "--output-dir",
                directory,
                *args,
            ],
            env=os.environ
            | {"API_BASE_URL": url, "GATEWAY_API_KEY": "qa-local-test-token"},
            text=True,
            capture_output=True,
            timeout=15,
            cwd=directory,
        )

    def serve(self, replies):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append((self.path, self.headers["Authorization"], body))
                status, payload = replies[len(received) - 1]
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/api", received

    def reply(self, step):
        results = []
        for event, expected in zip(
            step["batch"]["events"], step["expected"], strict=True
        ):
            outcome, _, reason = expected.partition(":")
            result = {
                key: event[key] for key in ("device_id", "boot_id", "sequence_number")
            }
            result["outcome"] = outcome
            if reason:
                result["reason"] = reason
            results.append(result)
        return {"batch_id": "test-batch", "results": results}

    def test_cli_sends_all_exact_steps_and_asserts_negative_outcomes(self):
        steps = [step for case in load_scenarios("cli-test") for step in case["steps"]]
        url, received = self.serve([(200, self.reply(step)) for step in steps])
        result = self.run_cli(url=url)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary["passed"])
        self.assertEqual(len(summary["results"]), 8)
        self.assertEqual(len(received), 13)
        for step, (path, credential, body) in zip(steps, received, strict=True):
            self.assertEqual(path, "/api/v1/telemetry/batches")
            self.assertEqual(credential, "Bearer qa-local-test-token")
            self.assertEqual(body, encode_batch(step["batch"]))
        report = Path(summary["fixtures"]) / "report.json"
        self.assertEqual(json.loads(report.read_bytes()), summary)
        self.assertNotIn("qa-local-test-token", report.read_text())

    def test_wrong_outcome_identity_missing_results_or_status_fail_and_skip_retry(self):
        step = load_scenarios("cli-test", names=["duplicate"])[0]["steps"][0]
        correct = self.reply(step)
        for status, payload in (
            (
                200,
                correct
                | {"results": [correct["results"][0] | {"outcome": "duplicate"}]},
            ),
            (
                200,
                correct | {"results": [correct["results"][0] | {"boot_id": "wrong"}]},
            ),
            (200, correct | {"results": []}),
            (201, correct),
            (401, {"detail": "qa-local-test-token"}),
            (503, {"detail": "unavailable"}),
        ):
            with self.subTest(status=status, payload=payload):
                url, received = self.serve([(status, payload)])
                result = self.run_cli("--scenario", "duplicate", url=url)
                self.assertEqual(result.returncode, 1, result.stderr)
                summary = json.loads(result.stdout)
                self.assertFalse(summary["passed"])
                self.assertEqual(summary["results"][0]["skipped_steps"], 1)
                self.assertEqual(len(received), 1)
                self.assertNotIn("qa-local-test-token", result.stdout + result.stderr)

    def test_list_export_only_and_bad_options_do_not_need_a_backend(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 8)
        result = self.run_cli("--scenario", "mixed-batch", "--export-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["mode"], "export-only")
        self.assertNotIn("passed", summary)
        for args in (("--scenario", "typo"), ("--timeout", "nan"), ("--timeout", "0")):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
