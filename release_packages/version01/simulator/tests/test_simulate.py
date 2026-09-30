import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from events import Scenario
from simulate import run_scenario

SCRIPT = Path(__file__).resolve().parents[1] / "simulate.py"


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.scenario = Scenario(device_id="device-test", run_id="test", count=5)

    def test_batches_wait_for_last_sample_without_network_drift(self):
        clock = FakeClock()
        sent_at = []

        def send(body, events):
            sent_at.append(clock.now)
            clock.now += 0.2
            return {}, ["accepted"] * len(events)

        summary = run_scenario(
            self.scenario, 2, send=send, clock=clock.clock, sleep=clock.sleep
        )
        self.assertEqual(sent_at, [101, 103, 104])
        self.assertEqual(summary["counts"]["accepted"], 5)
        self.assertEqual(summary["unconfirmed"], 0)
        self.assertEqual(summary["unsent"], 0)

    def test_slow_transport_is_reported_and_fast_mode_never_sleeps(self):
        for paced in (True, False):
            clock = FakeClock()

            def send(body, events, clock=clock):
                clock.now += 3
                return {}, ["accepted"] * len(events)

            summary = run_scenario(
                self.scenario,
                2,
                send=send,
                paced=paced,
                clock=clock.clock,
                sleep=clock.sleep,
            )
            self.assertEqual(summary["max_schedule_lag_seconds"], 3 if paced else 0)
            if not paced:
                self.assertEqual(clock.waits, [])

    def test_transport_failure_keeps_batch_unconfirmed_and_stops(self):
        sent = []

        def send(body, events):
            sent.append(body)
            if len(sent) == 2:
                raise urllib.error.URLError("synthetic failure")
            return {}, ["duplicate"] * len(events)

        summary = run_scenario(self.scenario, 2, send=send, paced=False)
        self.assertEqual(summary["counts"]["duplicate"], 2)
        self.assertEqual(summary["sent"], 4)
        self.assertEqual(summary["unconfirmed"], 2)
        self.assertEqual(summary["unsent"], 1)
        self.assertEqual(summary["failures"], 1)

    def test_cancellation_accounts_for_pending_or_in_flight_events(self):
        for interrupt_in_send in (False, True):
            clock = FakeClock()

            def interrupt(*args):
                raise KeyboardInterrupt

            summary = run_scenario(
                self.scenario,
                2,
                send=interrupt,
                clock=clock.clock,
                sleep=clock.sleep if interrupt_in_send else interrupt,
            )
            self.assertTrue(summary["cancelled"])
            self.assertEqual(summary["unconfirmed"], 2 if interrupt_in_send else 0)
            self.assertEqual(summary["unsent"], 3 if interrupt_in_send else 5)


@contextmanager
def api_server(response_mode="accepted"):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append((self.path, self.headers.get("Authorization"), body))
            events = json.loads(body)["events"]
            if response_mode == "redirect":
                self.send_response(307)
                self.send_header("Location", "/unexpected-target")
                self.end_headers()
                return
            if response_mode == "unavailable":
                self.send_response(503)
                self.end_headers()
                return
            if response_mode == "truncated":
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b'{"batch_id":')
                return
            results = []
            for event in events:
                item = {
                    k: event[k] for k in ("device_id", "boot_id", "sequence_number")
                }
                item["outcome"] = response_mode
                if response_mode == "rejected":
                    item["reason"] = "unknown_device"
                results.append(item)
            if response_mode == "incomplete":
                results = []
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"batch_id": "test", "results": results}).encode()
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class SimulatorCliTests(unittest.TestCase):
    def cli(self, *args, target="http://127.0.0.1:1/api", token="test-only-token"):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--device-id",
                "device-test",
                "--run-id",
                "cli-test",
                "--count",
                "5",
                "--batch-size",
                "2",
                "--reboot-every",
                "3",
                *args,
            ],
            env=os.environ | {"API_BASE_URL": target, "GATEWAY_API_KEY": token},
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_offline_generation_is_repeatable_without_network_or_credentials(self):
        first = self.cli("--seed", "7", "--noise", "0.5", token="")
        second = self.cli("--seed", "7", "--noise", "0.5", token="")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(len(first.stdout.splitlines()), 3)
        self.assertEqual(json.loads(first.stderr)["emitted"], 5)

    def test_http_sends_exact_generated_payloads_and_counts_confirmations(self):
        generated = self.cli()
        for outcome in ("accepted", "duplicate"):
            with (
                self.subTest(outcome=outcome),
                api_server(outcome) as (target, requests),
            ):
                result = self.cli("--mode", "http", "--fast", target=target)
                self.assertEqual(result.returncode, 0, result.stderr)
                summary = json.loads(result.stdout)
                self.assertEqual(summary["counts"][outcome], 5)
                self.assertEqual(summary["unconfirmed"], 0)
                self.assertEqual(summary["unsent"], 0)
                self.assertEqual(
                    [body.decode() for _, _, body in requests],
                    generated.stdout.splitlines(),
                )
                for path, authorization, _ in requests:
                    self.assertEqual(path, "/api/v1/telemetry/batches")
                    self.assertEqual(authorization, "Bearer test-only-token")
                self.assertNotIn("test-only-token", result.stdout + result.stderr)

    def test_rejected_items_are_confirmed_failures(self):
        with api_server("rejected") as (target, _):
            result = self.cli("--mode", "http", "--fast", target=target)
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["counts"]["rejected"], 5)
        self.assertEqual(summary["rejection_reasons"], {"unknown_device": 5})
        self.assertEqual(summary["unconfirmed"], 0)

    def test_invalid_responses_and_http_failures_stop_without_retry_or_redirect(self):
        for mode in ("incomplete", "unavailable", "redirect", "truncated"):
            with self.subTest(mode=mode), api_server(mode) as (target, requests):
                result = self.cli("--mode", "http", "--fast", target=target)
                self.assertEqual(result.returncode, 1, result.stderr)
                summary = json.loads(result.stdout)
                self.assertEqual(summary["unconfirmed"], 2)
                self.assertEqual(summary["unsent"], 3)
                self.assertEqual(len(requests), 1)

    def test_invalid_scenario_fails_before_http_writes(self):
        with api_server() as (target, requests):
            for args in (
                ("--count", "0"),
                ("--temperature", "nan"),
                ("--interval-ms", "-1"),
                ("--batch-size", "501"),
                ("--start-time", "2026-09-25"),
                ("--timeout", "inf"),
            ):
                with self.subTest(args=args):
                    result = self.cli("--mode", "http", "--fast", *args, target=target)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(requests, [])
