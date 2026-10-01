"""Registration and presence persisted through the device API."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from postgres_test_case import PostgresTestCase
from sqlalchemy import select, update

from app.main import create_app
from app.models import Device
from app.mqtt_admin import BrokerUnavailable
from app.seed import GATEWAY_ID


class DeviceManagementTests(PostgresTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()
        self.broker = Mock()
        self.broker.create_device.return_value = True
        self.broker.ensure_device.return_value = True
        self.broker.disable_device.return_value = True

    def app(self):
        return create_app(
            engine_factory=lambda: self.engine,
            broker_factory=lambda: self.broker,
        )

    def test_register_heartbeat_expire_and_reload(self) -> None:
        registration = {
            "device_id": "esp32-boiler-01",
            "gateway_id": GATEWAY_ID,
            "name": "Boiler room ESP32",
            "password": "long-device-password-123",
        }
        with patch.dict("os.environ", self.environment):
            with TestClient(self.app()) as client:
                gateways = client.get("/api/v1/gateways")
                self.assertEqual(gateways.status_code, 200)
                self.assertIn(GATEWAY_ID, str(gateways.json()))
                created = client.post("/api/v1/devices", json=registration)
                self.assertEqual(created.status_code, 201, created.text)
                self.assertFalse(created.json()["online"])
                self.assertNotIn("password", created.text)
                self.broker.create_device.assert_called_once_with(
                    registration["device_id"], registration["password"]
                )
                self.assertEqual(
                    client.post("/api/v1/devices", json=registration).status_code, 409
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/devices/esp32-boiler-01/heartbeat",
                        json={"password": "wrong-password"},
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/devices/esp32-boiler-01/heartbeat",
                        json={"password": registration["password"]},
                    ).status_code,
                    204,
                )
                current = {
                    d["device_id"]: d
                    for d in client.get("/api/v1/devices").json()["devices"]
                }
                self.assertTrue(current[registration["device_id"]]["online"])
                self.assertIsNotNone(current[registration["device_id"]]["last_seen_at"])
            # A new application process uses the saved rows, not in-memory state.
            with TestClient(self.app()) as restarted:
                current = {
                    d["device_id"]: d
                    for d in restarted.get("/api/v1/devices").json()["devices"]
                }
                self.assertTrue(current[registration["device_id"]]["online"])
                with self.engine.begin() as connection:
                    connection.execute(
                        update(Device)
                        .where(Device.device_id == registration["device_id"])
                        .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=2))
                    )
                current = {
                    d["device_id"]: d
                    for d in restarted.get("/api/v1/devices").json()["devices"]
                }
                self.assertFalse(current[registration["device_id"]]["online"])
                removed = restarted.delete(
                    f"/api/v1/devices/{registration['device_id']}"
                )
                self.assertEqual(removed.status_code, 204, removed.text)
                self.broker.disable_device.assert_called_once_with(
                    registration["device_id"]
                )
                self.broker.delete_device.assert_called_once_with(
                    registration["device_id"]
                )
                self.assertEqual(
                    restarted.delete(
                        f"/api/v1/devices/{registration['device_id']}"
                    ).status_code,
                    404,
                )
                device_ids = {
                    item["device_id"]
                    for item in restarted.get("/api/v1/devices").json()["devices"]
                }
                self.assertNotIn(registration["device_id"], device_ids)
                self.assertEqual(
                    restarted.post("/api/v1/devices", json=registration).status_code,
                    201,
                )
        with self.engine.connect() as connection:
            saved = connection.execute(
                select(Device.password_hash).where(
                    Device.device_id == registration["device_id"]
                )
            ).scalar_one()
        self.assertNotEqual(saved, registration["password"])
        self.assertTrue(saved.startswith("pbkdf2_sha256$"))

    def test_recent_esp32_telemetry_marks_online_but_queued_data_does_not(self) -> None:
        device_id = "esp32-pump-01"
        token = "gateway-test-token"
        environment = self.environment | {
            "GATEWAY_CREDENTIALS_JSON": json.dumps({GATEWAY_ID: token})
        }
        with patch.dict("os.environ", environment):
            with TestClient(self.app()) as client:
                created = client.post(
                    "/api/v1/devices",
                    json={
                        "device_id": device_id,
                        "gateway_id": GATEWAY_ID,
                        "name": "Pump ESP32",
                        "password": "another-long-password",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)

                def send(sequence: int, received_at: datetime):
                    return client.post(
                        "/api/v1/telemetry/batches",
                        headers={"Authorization": f"Bearer {token}"},
                        json={
                            "schema_version": 1,
                            "events": [
                                {
                                    "device_id": device_id,
                                    "boot_id": "boot-one",
                                    "sequence_number": sequence,
                                    "measured_at": received_at.isoformat(),
                                    "device_uptime_ms": sequence * 1000,
                                    "gateway_received_at": received_at.isoformat(),
                                    "metric": "temperature",
                                    "value": 24,
                                    "unit": "celsius",
                                    "quality": {
                                        "reading": "valid",
                                        "clock": "synchronised",
                                    },
                                }
                            ],
                        },
                    )

                recent = send(1, datetime.now(UTC))
                self.assertEqual(recent.status_code, 200, recent.text)
                self.assertEqual(recent.json()["results"][0]["outcome"], "accepted")
                devices = {
                    item["device_id"]: item
                    for item in client.get("/api/v1/devices").json()["devices"]
                }
                self.assertTrue(devices[device_id]["online"])
                with self.engine.begin() as connection:
                    connection.execute(
                        update(Device)
                        .where(Device.device_id == device_id)
                        .values(last_seen_at=datetime.now(UTC) - timedelta(minutes=2))
                    )
                queued = send(2, datetime.now(UTC) - timedelta(minutes=3))
                self.assertEqual(queued.status_code, 200, queued.text)
                self.assertEqual(queued.json()["results"][0]["outcome"], "accepted")
                devices = {
                    item["device_id"]: item
                    for item in client.get("/api/v1/devices").json()["devices"]
                }
                self.assertFalse(devices[device_id]["online"])
                blocked = client.delete(f"/api/v1/devices/{device_id}")
                self.assertEqual(blocked.status_code, 409, blocked.text)
                self.assertEqual(
                    blocked.json()["detail"]["reason"], "device_has_history"
                )
                device_ids = {
                    item["device_id"]
                    for item in client.get("/api/v1/devices").json()["devices"]
                }
                self.assertIn(device_id, device_ids)

    def test_existing_registration_can_set_up_mqtt_with_its_password(self) -> None:
        registration = {
            "device_id": "esp-nano",
            "gateway_id": GATEWAY_ID,
            "name": "ESP nano",
            "password": "long-device-password-123",
        }
        with patch.dict("os.environ", self.environment):
            with TestClient(self.app()) as client:
                self.assertEqual(
                    client.post("/api/v1/devices", json=registration).status_code, 201
                )
                with self.engine.begin() as connection:
                    connection.execute(
                        update(Device)
                        .where(Device.device_id == "esp-nano")
                        .values(mqtt_managed=False)
                    )
                address = "/api/v1/devices/esp-nano/mqtt"
                self.assertEqual(
                    client.post(
                        address, json={"password": "wrong-password"}
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    client.post(
                        address, json={"password": registration["password"]}
                    ).status_code,
                    204,
                )
                self.broker.ensure_device.assert_called_once_with(
                    "esp-nano", registration["password"]
                )
                with self.engine.connect() as connection:
                    self.assertTrue(
                        connection.execute(
                            select(Device.mqtt_managed).where(
                                Device.device_id == "esp-nano"
                            )
                        ).scalar_one()
                    )

    def test_broker_failure_leaves_no_registration(self) -> None:
        self.broker.create_device.side_effect = BrokerUnavailable("broker unavailable")
        with patch.dict("os.environ", self.environment):
            with TestClient(self.app()) as client:
                response = client.post(
                    "/api/v1/devices",
                    json={
                        "device_id": "broker-down-device",
                        "gateway_id": GATEWAY_ID,
                        "name": "Broker down",
                        "password": "long-device-password-123",
                    },
                )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.json()["detail"]["reason"], "mqtt_broker_unavailable"
                )
                self.assertNotIn(
                    "broker-down-device",
                    {
                        item["device_id"]
                        for item in client.get("/api/v1/devices").json()["devices"]
                    },
                )
