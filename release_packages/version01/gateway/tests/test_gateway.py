"""Black-box startup and shutdown checks for the native gateway executable."""

import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest


SETTINGS = (
    "MQTT_HOST",
    "MQTT_PORT",
    "MQTT_USERNAME",
    "MQTT_PASSWORD_FILE",
    "API_BASE_URL",
    "GATEWAY_API_KEY",
    "QUEUE_DB_PATH",
)


class GatewayProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = Path(sys.argv[1]).resolve()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / "mqtt.password").write_text("test-password\n")
        self.config_file = self.directory / "gateway.env"
        self.database = self.directory / "queue.sqlite3"
        # Reserve a port without listening so the broker is always unavailable.
        mqtt_socket = socket.socket()
        self.addCleanup(mqtt_socket.close)
        mqtt_socket.bind(("127.0.0.1", 0))
        self.values = {
            "MQTT_HOST": "127.0.0.1",
            "MQTT_PORT": str(mqtt_socket.getsockname()[1]),
            "MQTT_USERNAME": "gateway-test",
            "MQTT_PASSWORD_FILE": "mqtt.password",
            "API_BASE_URL": "http://127.0.0.1:8000/api",
            "GATEWAY_API_KEY": "test-token-123456",
            "QUEUE_DB_PATH": "queue.sqlite3",
        }
        self.environment = os.environ.copy()
        for setting in SETTINGS:
            self.environment.pop(setting, None)

    def write_config(self, values=None):
        values = self.values if values is None else values
        self.config_file.write_text(
            "# Gateway process test\n"
            + "\n".join(f"{key}={value}" for key, value in values.items())
            + "\n"
        )

    def run_check(self, environment=None):
        return subprocess.run(
            [self.executable, "--config", self.config_file, "--check-config"],
            capture_output=True,
            text=True,
            env=environment or self.environment,
            timeout=5,
            check=False,
        )

    def start_and_stop(self):
        process = subprocess.Popen(
            [self.executable, "--config", self.config_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment,
        )
        try:
            time.sleep(0.05)
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            output, errors = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, errors)
            events = [json.loads(line)["event"] for line in output.splitlines()]
            self.assertIn("ready", events)
            self.assertEqual(events[-2:], ["shutdown_requested", "stopped"])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_config_validation_and_environment_precedence(self):
        self.write_config()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["event"], "config_valid")
        self.assertFalse(self.database.exists())

        invalid = dict(self.values, MQTT_PORT="invalid")
        self.write_config(invalid)
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("MQTT_PORT", json.loads(result.stderr)["message"])

        environment = dict(self.environment, MQTT_PORT="1884")
        self.assertEqual(self.run_check(environment).returncode, 0)

    def test_config_errors_are_clear_and_do_not_expose_secrets(self):
        cases = (
            ({key: value for key, value in self.values.items() if key != "MQTT_HOST"},
             "MQTT_HOST"),
            (dict(self.values, MQTT_PASSWORD_FILE="missing.password"),
             "MQTT_PASSWORD_FILE"),
            (dict(self.values, API_BASE_URL="http://127.0.0.1:8000"),
             "API_BASE_URL"),
            (dict(self.values, GATEWAY_API_KEY="replace-with-credential"),
             "GATEWAY_API_KEY"),
            (dict(self.values, MQTT_HSOT="typo"), "MQTT_HSOT"),
        )
        for values, expected in cases:
            with self.subTest(setting=expected):
                self.write_config(values)
                result = self.run_check()
                self.assertEqual(result.returncode, 2)
                record = json.loads(result.stderr)
                self.assertEqual(record["event"], "invalid_config")
                self.assertIn(expected, record["message"])
                self.assertNotIn("test-token-123456", result.stderr)
                self.assertNotIn("test-password", result.stderr)

    def test_sigterm_closes_sqlite_and_preserves_existing_data(self):
        self.write_config()
        self.start_and_stop()
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)

        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
            connection.execute("INSERT INTO marker VALUES ('retained')")

        self.start_and_stop()
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(connection.execute("SELECT value FROM marker").fetchone(),
                             ("retained",))

    def test_storage_open_failure_is_reported(self):
        self.write_config(dict(self.values, QUEUE_DB_PATH="missing/queue.sqlite3"))
        result = subprocess.run(
            [self.executable, "--config", self.config_file],
            capture_output=True,
            text=True,
            env=self.environment,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stderr)["event"], "storage_error")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
