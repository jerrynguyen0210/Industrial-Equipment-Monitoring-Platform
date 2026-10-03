"""Dashboard reads verified against PostgreSQL and the HTTP response contract."""

import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.db.models import Device, Telemetry
from app.db.seed import DEVICE_ID, GATEWAY_ID
from app.main import create_app
from fastapi.testclient import TestClient
from postgres_test_case import PostgresTestCase
from sqlalchemy import insert, text

BASE = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
DEVICE_URL = "/api/v1/devices"
HISTORY_URL = f"{DEVICE_URL}/{DEVICE_ID}/telemetry"


def reading(number: int, minute: int, **changes) -> dict:
    return {
        "schema_version": 1,
        "device_id": DEVICE_ID,
        "boot_id": "boot-a",
        "sequence_number": number,
        "measured_at": BASE + timedelta(minutes=minute),
        "device_uptime_ms": number * 1000,
        "gateway_received_at": BASE + timedelta(minutes=minute, seconds=1),
        "metric": "temperature",
        "value": Decimal(number),
        "unit": "celsius",
        "quality": {"reading": "valid", "clock": "synchronised"},
        **changes,
    }


class ReadModelTests(PostgresTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()
        self.token = secrets.token_urlsafe(24)
        self.enterContext(
            patch.dict(
                os.environ,
                self.environment
                | {"GATEWAY_CREDENTIALS_JSON": json.dumps({GATEWAY_ID: self.token})},
            )
        )
        self.client = self.enterContext(
            TestClient(create_app(engine_factory=lambda: self.engine))
        )

    def insert(self, *rows: dict) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(Telemetry), list(rows))

    def post(self, row: dict):
        item = {key: value for key, value in row.items() if key != "schema_version"}
        for key, value in item.items():
            if isinstance(value, datetime):
                item[key] = value.isoformat()
            elif isinstance(value, Decimal):
                item[key] = int(value)
        return self.client.post(
            "/api/v1/telemetry/batches",
            json={"schema_version": 1, "events": [item]},
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def history(
        self, start: datetime = BASE, end: datetime = BASE + timedelta(hours=1)
    ):
        return self.client.get(
            HISTORY_URL,
            params={"from": start.isoformat(), "to": end.isoformat()},
        )

    def test_event_time_index_matches_the_query_order(self) -> None:
        with self.engine.connect() as connection:
            definition = connection.scalar(
                text(
                    "SELECT pg_get_indexdef(indexrelid) FROM pg_index "
                    "JOIN pg_class ON pg_class.oid = indexrelid "
                    "WHERE relname = 'ix_telemetry_device_event_at'"
                )
            )
        self.assertIsNotNone(definition)
        for fragment in (
            "device_id",
            "measured_at",
            "quality ->> 'clock'",
            "gateway_received_at",
            "id DESC",
        ):
            self.assertIn(fragment, definition)

    def test_current_reading_survives_older_replay(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(Device).values(
                    device_id="empty-device", gateway_id=GATEWAY_ID, name="Empty"
                )
            )
        newer = reading(20, 20)
        older = reading(10, 10, boot_id="old-boot")
        self.assertEqual(self.post(newer).json()["results"][0]["outcome"], "accepted")
        self.assertEqual(self.post(older).json()["results"][0]["outcome"], "accepted")
        retry = self.post(older | {"gateway_received_at": BASE + timedelta(minutes=21)})
        self.assertEqual(retry.json()["results"][0]["outcome"], "duplicate")

        response = self.client.get(DEVICE_URL)
        self.assertEqual(response.status_code, 200, response.text)
        devices = {item["device_id"]: item for item in response.json()["devices"]}
        self.assertIsNone(devices["empty-device"]["latest_reading"])
        latest = devices[DEVICE_ID]["latest_reading"]
        self.assertEqual(latest["value"], "20")
        self.assertEqual(latest["unit"], "celsius")
        self.assertEqual(latest["timestamp_source"], "measured_at")
        self.assertEqual(
            datetime.fromisoformat(latest["event_at"]), BASE + timedelta(minutes=20)
        )
        self.assertEqual(
            datetime.fromisoformat(latest["gateway_received_at"]),
            BASE + timedelta(minutes=20, seconds=1),
        )

    def test_history_orders_fallback_timestamps_and_preserves_sources(self) -> None:
        # Insertion order differs from event order, and one unsynchronised row
        # supplies a measurement time which must not control its position.
        self.insert(
            reading(30, 30),
            reading(
                10,
                50,
                gateway_received_at=BASE + timedelta(minutes=10),
                quality={"reading": "valid", "clock": "unsynchronised"},
            ),
            reading(
                20,
                20,
                measured_at=None,
                gateway_received_at=BASE + timedelta(minutes=20),
                quality={"reading": "valid", "clock": "unknown"},
            ),
            reading(60, 60),
        )
        response = self.history()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["unit"], "celsius")
        self.assertFalse(result["truncated"])
        self.assertEqual(
            [point["value"] for point in result["points"]], ["10", "20", "30"]
        )
        self.assertEqual(
            [point["timestamp_source"] for point in result["points"]],
            ["gateway_received_at", "gateway_received_at", "measured_at"],
        )
        self.assertEqual(
            [datetime.fromisoformat(point["event_at"]) for point in result["points"]],
            [BASE + timedelta(minutes=minute) for minute in (10, 20, 30)],
        )
        self.assertEqual(
            datetime.fromisoformat(result["points"][0]["measured_at"]),
            BASE + timedelta(minutes=50),
        )
        self.assertIsNone(result["points"][1]["measured_at"])
        self.assertTrue(all(point["unit"] == "celsius" for point in result["points"]))
        self.assertTrue(all(point["gateway_received_at"] for point in result["points"]))
        self.assertTrue(all(point["gap_before"] for point in result["points"]))

        current = self.client.get(DEVICE_URL).json()["devices"][0]["latest_reading"]
        self.assertEqual(current["value"], "60")

    def test_bounded_range_errors_and_legacy_alias(self) -> None:
        self.insert(reading(0, 0), reading(1, 1), reading(2, 2))
        response = self.history(BASE, BASE + timedelta(minutes=2))
        self.assertEqual(
            [point["value"] for point in response.json()["points"]], ["0", "1"]
        )
        legacy = self.client.get(
            HISTORY_URL + "/history",
            params={
                "from": BASE.isoformat(),
                "to": (BASE + timedelta(minutes=2)).isoformat(),
            },
        )
        self.assertEqual(legacy.json(), response.json())
        for params in (
            {"from": BASE.isoformat(), "to": BASE.isoformat()},
            {"from": BASE.isoformat(), "to": (BASE + timedelta(days=8)).isoformat()},
            {
                "from": "2026-09-29T00:00:00",
                "to": (BASE + timedelta(hours=1)).isoformat(),
            },
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get(HISTORY_URL, params=params).status_code, 422
                )
        unknown = self.client.get(
            f"{DEVICE_URL}/missing/telemetry",
            params={
                "from": BASE.isoformat(),
                "to": (BASE + timedelta(hours=1)).isoformat(),
            },
        )
        self.assertEqual(unknown.status_code, 404)

    def test_history_caps_points_and_keeps_newest_window(self) -> None:
        self.insert(
            *[
                reading(number, 0, measured_at=BASE + timedelta(seconds=number))
                for number in range(2001)
            ]
        )
        response = self.history()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["points"]), 2000)
        self.assertEqual(result["points"][0]["value"], "1")
        self.assertEqual(result["points"][-1]["value"], "2000")
