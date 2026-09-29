"""Exercise MQTT intake against a real local Mosquitto broker."""

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


class MqttIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = Path(sys.argv[1]).resolve()
        cls.broker = Path(sys.argv[2]).resolve()
        cls.publisher = Path(sys.argv[3]).resolve()
        cls.password_tool = Path(sys.argv[4]).resolve()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        with socket.socket() as temporary_socket:
            temporary_socket.bind(("127.0.0.1", 0))
            self.port = temporary_socket.getsockname()[1]
        passwords = self.directory / "passwd"
        for flags, username, password in (
            (["-b", "-c"], "gateway-test", "test-password"),
            (["-b"], "device-demo-001", "device-password"),
            (["-b"], "another-device", "device-password"),
        ):
            subprocess.run(
                [self.password_tool, *flags, passwords, username, password],
                check=True,
                capture_output=True,
                timeout=5,
            )
        acl = self.directory / "acl"
        acl.write_text(
            "user gateway-test\ntopic read equipment/+/telemetry\n"
            "user device-demo-001\ntopic write equipment/device-demo-001/telemetry\n"
            "user another-device\ntopic write equipment/another-device/telemetry\n"
        )
        broker_config = self.directory / "mosquitto.conf"
        broker_config.write_text(
            f"listener {self.port} 127.0.0.1\nallow_anonymous false\n"
            f"password_file {passwords}\nacl_file {acl}\npersistence false\n"
        )
        self.broker_process = subprocess.Popen(
            [self.broker, "-c", broker_config],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(self.stop_broker)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.broker_process.poll() is not None:
                self.fail("test broker exited before listening")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("test broker did not start")

        (self.directory / "mqtt.password").write_text("test-password\n")
        self.database = self.directory / "queue.sqlite3"
        self.config = self.directory / "gateway.env"
        self.config.write_text(
            f"MQTT_HOST=127.0.0.1\nMQTT_PORT={self.port}\n"
            "MQTT_USERNAME=gateway-test\nMQTT_PASSWORD_FILE=mqtt.password\n"
            "API_BASE_URL=http://127.0.0.1:8000/api\n"
            "GATEWAY_API_KEY=test-token-123456\nQUEUE_DB_PATH=queue.sqlite3\n"
        )
        self.start_gateway()
        self.addCleanup(self.stop_gateway)

    def start_gateway(self):
        self.records = queue.Queue()
        self.gateway_process = subprocess.Popen(
            [self.gateway, "--config", self.config],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for stream in (self.gateway_process.stdout, self.gateway_process.stderr):
            threading.Thread(target=self.collect_logs, args=(stream,), daemon=True).start()
        pending_loaded = self.wait_for("pending_loaded")
        self.wait_for("subscribed")
        return pending_loaded

    def collect_logs(self, stream):
        for line in stream:
            self.records.put(json.loads(line))

    def wait_for(self, event, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.gateway_process.poll() is not None:
                self.fail(f"gateway exited while waiting for {event}")
            try:
                record = self.records.get(timeout=min(0.2, deadline - time.monotonic()))
            except queue.Empty:
                continue
            if record["event"] == event:
                return record
        self.fail(f"gateway did not log {event}")

    def publish(self, payload, topic="equipment/device-demo-001/telemetry"):
        publisher_name = "another-device" if "another-device" in topic else "device-demo-001"
        subprocess.run(
            [self.publisher, "-h", "127.0.0.1", "-p", str(self.port),
             "-u", publisher_name, "-P", "device-password",
             "-q", "1", "-t", topic, "-m", payload],
            check=True,
            timeout=5,
            capture_output=True,
        )

    def stop_gateway(self):
        if self.gateway_process.poll() is None:
            self.gateway_process.send_signal(signal.SIGTERM)
            try:
                self.gateway_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.gateway_process.kill()
                self.gateway_process.wait(timeout=5)

    def stop_broker(self):
        if self.broker_process.poll() is None:
            self.broker_process.terminate()
            self.broker_process.wait(timeout=5)

    def row(self, sequence_number):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT mqtt_payload, gateway_received_at FROM intake_events "
                "WHERE device_id=? AND boot_id=? AND sequence_number=?",
                ("device-demo-001", "mqtt-local-demo-1", sequence_number),
            ).fetchone()

    def queue_metadata(self, sequence_number):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT queue_state, attempt_count FROM intake_events "
                "WHERE device_id=? AND boot_id=? AND sequence_number=?",
                ("device-demo-001", "mqtt-local-demo-1", sequence_number),
            ).fetchone()

    def test_original_receipt_and_rejections(self):
        sample = Path(__file__).resolve().parents[2] / "infra/mosquitto/sample-event.json"
        valid = sample.read_text()
        self.publish(valid)
        self.wait_for("message_stored")
        payload, received_at = self.row(0)
        self.assertEqual(payload, valid)
        self.assertEqual(self.queue_metadata(0), ("pending", 0))
        self.assertRegex(received_at, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        self.assertNotIn("gateway_received_at", json.loads(payload))

        self.publish(valid)
        self.wait_for("message_duplicate")
        self.assertEqual(self.row(0), (payload, received_at))

        changed = valid.replace("31.4", "32.4")
        self.publish(changed)
        self.wait_for("identity_conflict")
        self.assertEqual(self.row(0), (payload, received_at))

        missing = json.loads(valid)
        del missing["quality"]
        self.publish(json.dumps(missing))
        self.assertEqual(self.wait_for("message_rejected")["message"], "invalid_event_fields")
        self.publish("{bad json")
        self.assertEqual(self.wait_for("message_rejected")["message"], "invalid_json")

        variants = (
            (valid.replace('"schema_version": 1', '"schema_version": 1.0'),
             "unsupported_schema_version", "equipment/device-demo-001/telemetry"),
            (valid.replace('"sequence_number": 0', '"sequence_number": true'),
             "invalid_sequence_number", "equipment/device-demo-001/telemetry"),
            (valid.replace('"measured_at": null',
                           '"measured_at": "2026-02-30T12:00:00Z"'),
             "invalid_measured_at", "equipment/device-demo-001/telemetry"),
            (valid.replace('"quality":', '"quality": {"reading": "valid"}, "quality":'),
             "duplicate_json_key", "equipment/device-demo-001/telemetry"),
            (valid, "topic_device_mismatch", "equipment/another-device/telemetry"),
        )
        for bad_payload, reason, topic in variants:
            with self.subTest(reason=reason):
                self.publish(bad_payload, topic)
                self.assertEqual(self.wait_for("message_rejected")["message"], reason)

        forged = json.loads(valid)
        forged["sequence_number"] = 2
        forged["gateway_received_at"] = "2000-01-01T00:00:00Z"
        self.publish(json.dumps(forged))
        self.assertEqual(self.wait_for("message_rejected")["message"], "gateway_received_at_forbidden")
        self.assertIsNone(self.row(2))

        precise = valid.replace('"sequence_number": 0', '"sequence_number": 1').replace(
            "31.4", "31.4000000000000000000000001"
        )
        self.publish(precise)
        self.wait_for("message_stored")
        self.assertEqual(self.row(1)[0], precise)
        self.assertEqual(self.queue_metadata(1), ("pending", 0))

        # The stored log is emitted after SQLite commit. A hard process exit
        # must leave both rows available to the restarted gateway.
        self.gateway_process.kill()
        self.gateway_process.wait(timeout=5)
        pending_loaded = self.start_gateway()
        self.assertIn("2 of 2 pending rows", pending_loaded["message"])
        self.assertEqual(self.queue_metadata(0), ("pending", 0))
        self.publish(valid)
        self.wait_for("message_duplicate")
        self.assertEqual(self.row(0), (payload, received_at))
        self.stop_gateway()
        self.assertEqual(self.gateway_process.returncode, 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM intake_events").fetchone(),
                             (2,))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
