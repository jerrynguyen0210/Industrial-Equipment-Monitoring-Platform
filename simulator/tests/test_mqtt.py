import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from events import Scenario, TemperatureProfile, generate_events
from mqtt_transport import MqttPublisher, device_message, validate_mqtt_target
from simulate import run_mqtt_scenario

SCRIPT = Path(__file__).resolve().parents[1] / "simulate.py"


class FakeClock:
    def __init__(self):
        self.now = 10.0
        self.waits = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class MqttScenarioTests(unittest.TestCase):
    def test_device_payload_preserves_identity_and_omits_gateway_fields(self):
        scenario = Scenario(
            device_id="device-test",
            run_id="mqtt-test",
            count=5,
            reboot_every=3,
            profile=TemperatureProfile(kind="ramp", temperature=20, step=0.5),
        )
        clock = FakeClock()
        published = []

        def publish(event):
            published.append((clock.now, json.loads(device_message(event))))

        summary = run_mqtt_scenario(
            scenario, publish, clock=clock.clock, sleep=clock.sleep
        )
        self.assertEqual(summary["broker_acknowledged"], 5)
        self.assertEqual(summary["unconfirmed"], 0)
        self.assertEqual(summary["unsent"], 0)
        self.assertEqual([at for at, _ in published], [10, 11, 12, 13, 14])
        events = list(generate_events(scenario))
        self.assertEqual(
            [message for _, message in published],
            [
                {"schema_version": 1}
                | {
                    key: value
                    for key, value in event.items()
                    if key != "gateway_received_at"
                }
                for event in events
            ],
        )
        self.assertEqual(
            [item["sequence_number"] for _, item in published], [0, 1, 2, 0, 1]
        )
        self.assertNotEqual(published[0][1]["boot_id"], published[3][1]["boot_id"])
        self.assertEqual(
            [item["value"] for _, item in published], [20, 20.5, 21, 21.5, 22]
        )
        self.assertNotIn("gateway_received_at", published[0][1])

    def test_failure_stops_without_relabeling_unconfirmed_publish(self):
        scenario = Scenario(device_id="device-test", run_id="failure", count=5)
        seen = []

        def publish(event):
            seen.append(event)
            if len(seen) == 3:
                raise TimeoutError("lost acknowledgement")

        summary = run_mqtt_scenario(scenario, publish, paced=False)
        self.assertEqual(len(seen), 3)
        self.assertEqual(summary["sent"], 3)
        self.assertEqual(summary["broker_acknowledged"], 2)
        self.assertEqual(summary["unconfirmed"], 1)
        self.assertEqual(summary["unsent"], 2)
        self.assertEqual(summary["failures"], 1)

    def test_mqtt_target_and_password_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            password_file = Path(directory) / "device.password"
            password_file.write_text("local-test-secret\n", encoding="utf-8")
            self.assertEqual(
                validate_mqtt_target(
                    "device-test", "127.0.0.1", 1883, "device-test", password_file
                ),
                "local-test-secret",
            )
            for device_id in ("a/b", "a+", "a#"):
                with self.subTest(device_id=device_id):
                    with self.assertRaises(ValueError):
                        validate_mqtt_target(
                            device_id, "127.0.0.1", 1883, "device-test", password_file
                        )
            password_file.write_text("local-test-secret\nextra\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_mqtt_target(
                    "device-test", "127.0.0.1", 1883, "device-test", password_file
                )

    def test_cli_connection_failure_reports_unconfirmed_without_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            password_file = Path(directory) / "device.password"
            password_file.write_text("local-test-secret\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--device-id",
                    "device-test",
                    "--run-id",
                    "mqtt-failure",
                    "--count",
                    "3",
                    "--mode",
                    "mqtt",
                    "--fast",
                    "--mqtt-port",
                    "1",
                    "--mqtt-password-file",
                    str(password_file),
                ],
                env=os.environ | {"MQTT_USERNAME": "device-test"},
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["broker_acknowledged"], 0)
            self.assertEqual(summary["unconfirmed"], 1)
            self.assertEqual(summary["unsent"], 2)
            self.assertNotIn("local-test-secret", result.stdout + result.stderr)

    def test_cli_publishes_real_qos_one_packets_and_waits_for_puback(self):
        def exact(connection, size):
            result = bytearray()
            while len(result) < size:
                chunk = connection.recv(size - len(result))
                if not chunk:
                    raise ConnectionError("MQTT client closed before packet completed")
                result.extend(chunk)
            return bytes(result)

        def packet(connection):
            kind = exact(connection, 1)[0]
            multiplier = 1
            length = 0
            while True:
                digit = exact(connection, 1)[0]
                length += (digit & 127) * multiplier
                if not digit & 128:
                    break
                multiplier *= 128
            return kind, exact(connection, length)

        received = []
        errors = []
        with tempfile.TemporaryDirectory() as directory, socket.socket() as server:
            password_file = Path(directory) / "device.password"
            password_file.write_text("local-test-secret\n", encoding="utf-8")
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(5)

            def serve():
                try:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(5)
                        self.assertEqual(packet(connection)[0] >> 4, 1)
                        connection.sendall(b"\x20\x02\x00\x00")
                        for _ in range(3):
                            header, body = packet(connection)
                            topic_length = int.from_bytes(body[:2], "big")
                            topic = body[2 : 2 + topic_length].decode()
                            mid = body[2 + topic_length : 4 + topic_length]
                            payload = json.loads(body[4 + topic_length :])
                            received.append((header, topic, payload))
                            connection.sendall(b"\x40\x02" + mid)
                except Exception as error:
                    errors.append(error)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--device-id",
                    "device-test",
                    "--run-id",
                    "mqtt-wire",
                    "--count",
                    "3",
                    "--reboot-every",
                    "2",
                    "--profile",
                    "ramp",
                    "--temperature",
                    "20",
                    "--step",
                    "0.5",
                    "--mode",
                    "mqtt",
                    "--fast",
                    "--mqtt-port",
                    str(server.getsockname()[1]),
                    "--mqtt-password-file",
                    str(password_file),
                ],
                env=os.environ | {"MQTT_USERNAME": "device-test"},
                text=True,
                capture_output=True,
                timeout=15,
            )
            thread.join(timeout=5)
        self.assertFalse(errors, errors)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["broker_acknowledged"], 3)
        self.assertEqual([header for header, _, _ in received], [0x32] * 3)
        self.assertEqual(
            [topic for _, topic, _ in received],
            ["equipment/device-test/telemetry"] * 3,
        )
        self.assertEqual(
            [payload["sequence_number"] for _, _, payload in received], [0, 1, 0]
        )
        self.assertEqual(
            [payload["value"] for _, _, payload in received], [20, 20.5, 21]
        )
        self.assertNotEqual(received[0][2]["boot_id"], received[2][2]["boot_id"])
        self.assertNotIn("gateway_received_at", received[0][2])


class PublisherTests(unittest.TestCase):
    def test_qos_one_no_retain_and_puback_required(self):
        import paho.mqtt.client as mqtt

        class Info:
            rc = mqtt.MQTT_ERR_SUCCESS

            def __init__(self):
                self.waited = False

            def wait_for_publish(self, timeout):
                self.waited = True

            def is_published(self):
                return self.waited

        class Client:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.calls = []
                self.info = Info()

            def username_pw_set(self, username, password):
                self.credentials = (username, password)

            def connect(self, host, port, keepalive):
                self.on_connect(self, None, None, 0, None)
                return mqtt.MQTT_ERR_SUCCESS

            def loop_start(self):
                pass

            def publish(self, topic, payload, qos, retain):
                self.calls.append((topic, json.loads(payload), qos, retain))
                return self.info

            def disconnect(self):
                pass

            def loop_stop(self):
                pass

        with patch.object(mqtt, "Client", Client):
            publisher = MqttPublisher("127.0.0.1", 1883, "device-test", "secret", 1)
            publisher.publish(
                next(
                    generate_events(
                        Scenario(device_id="device-test", run_id="transport")
                    )
                )
            )
            publisher.close()
        self.assertEqual(publisher._client.credentials, ("device-test", "secret"))
        topic, payload, qos, retain = publisher._client.calls[0]
        self.assertEqual(topic, "equipment/device-test/telemetry")
        self.assertEqual(qos, 1)
        self.assertFalse(retain)
        self.assertEqual(payload["schema_version"], 1)
        self.assertNotIn("gateway_received_at", payload)


if __name__ == "__main__":
    unittest.main()
