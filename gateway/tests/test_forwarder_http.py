"""Exercise the gateway worker against a local HTTP backend stub."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = Path(sys.argv[1]).resolve()
        cls.broker = Path(sys.argv[2]).resolve()
        cls.password_tool = Path(sys.argv[3]).resolve()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / "queue.sqlite3"
        self.payloads = {}
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE intake_events (device_id TEXT NOT NULL, "
                "boot_id TEXT NOT NULL, sequence_number INTEGER NOT NULL, "
                "mqtt_payload TEXT NOT NULL, gateway_received_at TEXT NOT NULL, "
                "PRIMARY KEY(device_id,boot_id,sequence_number)) WITHOUT ROWID"
            )
            for sequence in (1, 2, 3):
                payload = (
                    '{"schema_version":1,"device_id":"device-1","boot_id":"boot-1",'
                    f'"sequence_number":{sequence},"measured_at":null,"device_uptime_ms":1,'
                    '"metric":"temperature","value":31.4000000000000000000000001,'
                    '"unit":"celsius","quality":{"reading":"valid",'
                    '"clock":"unsynchronised"}}'
                )
                self.payloads[sequence] = payload
                connection.execute(
                    "INSERT INTO intake_events VALUES (?,?,?,?,?)",
                    ("device-1", "boot-1", sequence, payload,
                     "2026-01-01T00:00:00.000Z"),
                )

        self.requests = queue.Queue()
        self.request_count = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.put((self.path, self.headers.get("Authorization"), body))
                owner.request_count += 1
                if owner.request_count == 1:
                    self.send_response(503)
                    self.end_headers()
                    return
                events = json.loads(body)["events"]
                outcomes = {1: "accepted", 2: "duplicate", 3: "rejected"}
                results = []
                for event in events:
                    outcome = outcomes[event["sequence_number"]]
                    result = {
                        "device_id": event["device_id"],
                        "boot_id": event["boot_id"],
                        "sequence_number": event["sequence_number"],
                        "outcome": outcome,
                    }
                    if outcome == "rejected":
                        result["reason"] = "unknown_device"
                    results.append(result)
                response = json.dumps({"batch_id": "test-batch", "results": results}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.stop_server)
        with socket.socket() as temporary_socket:
            temporary_socket.bind(("127.0.0.1", 0))
            mqtt_port = temporary_socket.getsockname()[1]
        password_file = self.directory / "broker-passwd"
        subprocess.run(
            [self.password_tool, "-b", "-c", password_file, "gateway-test", "test-password"],
            check=True, capture_output=True, timeout=5,
        )
        broker_config = self.directory / "mosquitto.conf"
        broker_config.write_text(
            f"listener {mqtt_port} 127.0.0.1\nallow_anonymous false\n"
            f"password_file {password_file}\npersistence false\n"
        )
        self.broker_process = subprocess.Popen(
            [self.broker, "-c", broker_config],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_broker)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.assertIsNone(self.broker_process.poll(), "test broker exited")
            try:
                with socket.create_connection(("127.0.0.1", mqtt_port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("test broker did not listen")
        (self.directory / "mqtt.password").write_text("test-password\n")
        self.config = self.directory / "gateway.env"
        self.config.write_text(
            "MQTT_HOST=127.0.0.1\n"
            f"MQTT_PORT={mqtt_port}\n"
            "MQTT_USERNAME=gateway-test\nMQTT_PASSWORD_FILE=mqtt.password\n"
            f"API_BASE_URL=http://127.0.0.1:{self.server.server_port}/api\n"
            "GATEWAY_API_KEY=test-token-123456\nQUEUE_DB_PATH=queue.sqlite3\n"
        )
        self.process = None
        self.addCleanup(self.stop_gateway)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=3)

    def stop_broker(self):
        if self.broker_process.poll() is None:
            self.broker_process.terminate()
            self.broker_process.wait(timeout=5)

    def start_gateway(self):
        self.records = queue.Queue()
        self.process = subprocess.Popen(
            [self.gateway, "--config", self.config],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for stream in (self.process.stdout, self.process.stderr):
            threading.Thread(target=self.collect, args=(stream,), daemon=True).start()

    def collect(self, stream):
        for line in stream:
            self.records.put(json.loads(line))

    def wait_for(self, event, timeout=6):
        deadline = time.monotonic() + timeout
        seen = []
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                seen.extend(list(self.records.queue))
                self.fail(f"gateway exited while waiting for {event}: {seen}")
            try:
                record = self.records.get(timeout=min(0.2, deadline - time.monotonic()))
            except queue.Empty:
                continue
            seen.append(record)
            if record["event"] == event:
                return record
        self.fail(f"gateway did not log {event}")

    def stop_gateway(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=5)
            self.assertEqual(self.process.returncode, 0)
        if self.process:
            self.process.stdout.close()
            self.process.stderr.close()

    def test_http_outcomes_after_restart(self):
        self.start_gateway()
        self.wait_for("delivery_deferred")
        path, credential, first_body = self.requests.get(timeout=2)
        self.assertEqual(path, "/api/v1/telemetry/batches")
        self.assertEqual(credential, "Bearer test-token-123456")
        self.assertIn(b"31.4000000000000000000000001", first_body)
        batch = json.loads(first_body)
        self.assertEqual(batch["schema_version"], 1)
        self.assertEqual(len(batch["events"]), 3)
        self.assertTrue(all("schema_version" not in item for item in batch["events"]))
        self.assertTrue(all(item["gateway_received_at"] == "2026-01-01T00:00:00.000Z"
                            for item in batch["events"]))
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM intake_events WHERE queue_state='pending' "
                "AND attempt_count=1"
            ).fetchone(), (3,))
        self.stop_gateway()

        self.start_gateway()
        self.assertIn("3 of 3 pending rows", self.wait_for("pending_loaded")["message"])
        self.wait_for("batch_applied")
        self.requests.get(timeout=2)
        self.stop_gateway()
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM intake_events").fetchone(),
                             (0,))
            self.assertEqual(connection.execute(
                "SELECT mqtt_payload, gateway_received_at, reason, attempt_count "
                "FROM quarantined_events WHERE sequence_number=3"
            ).fetchone(), (self.payloads[3], "2026-01-01T00:00:00.000Z",
                           "unknown_device", 2))
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
