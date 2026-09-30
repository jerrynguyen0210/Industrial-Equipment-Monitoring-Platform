"""Temperature alert transitions through authenticated ingestion and PostgreSQL."""

import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

from app.main import create_app
from app.models import AlertEpisode, AlertState, Telemetry
from app.seed import DEVICE_ID, GATEWAY_ID
from app.telemetry_openapi import VALID_EVENT
from fastapi.testclient import TestClient
from postgres_test_case import PostgresTestCase
from sqlalchemy import select
from sqlalchemy.orm import Session

ENDPOINT = "/api/v1/telemetry/batches"


class AlertingTests(PostgresTestCase):
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
        self.base_time = datetime.now(UTC) - timedelta(minutes=2)

    def reading(self, sequence: int, value: float, *, seconds: float | None = None):
        offset = seconds if seconds is not None else sequence
        at = self.base_time + timedelta(seconds=offset)
        timestamp = at.isoformat()
        return VALID_EVENT | {
            "device_id": DEVICE_ID,
            "boot_id": "alert-demo",
            "sequence_number": sequence,
            "measured_at": timestamp,
            "gateway_received_at": timestamp,
            "value": value,
        }

    def post(self, *items: dict):
        response = self.client.post(
            ENDPOINT,
            json={"schema_version": 1, "events": list(items)},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["results"]

    def episodes(self):
        with Session(self.engine) as session:
            return list(session.scalars(select(AlertEpisode).order_by(AlertEpisode.id)))

    def state(self):
        with Session(self.engine) as session:
            return session.get(AlertState, DEVICE_ID)

    def test_open_once_then_resolve_after_three_recovery_readings(self) -> None:
        high1, high2, high3 = (self.reading(n, 31) for n in (1, 2, 3))
        self.assertEqual(self.post(high1)[0]["outcome"], "accepted")
        self.assertEqual(self.post(high1)[0]["outcome"], "duplicate")
        self.post(high2)
        self.assertEqual(self.state().high_streak, 2)
        self.post(high3)
        self.assertEqual(len(self.episodes()), 1)
        self.assertIsNone(self.episodes()[0].resolved_at)

        self.post(self.reading(4, 32))
        self.post(self.reading(5, 27))
        self.assertEqual(self.post(self.reading(5, 27))[0]["outcome"], "duplicate")
        # Distinct identities can be stored but older event times do not count.
        self.post(self.reading(6, 27, seconds=4.5))
        self.post(self.reading(7, 27, seconds=-600))
        self.assertEqual(self.state().recovery_streak, 1)
        self.assertEqual(len(self.episodes()), 1)
        self.assertIsNone(self.episodes()[0].resolved_at)

        self.post(self.reading(8, 28))  # Strictly below 28 is required.
        self.assertEqual(self.state().recovery_streak, 0)
        self.post(self.reading(9, 27))
        self.post(self.reading(10, 27))
        self.assertIsNone(self.episodes()[0].resolved_at)
        self.post(self.reading(11, 27))
        episode = self.episodes()[0]
        self.assertEqual(episode.opened_at, self.base_time + timedelta(seconds=3))
        self.assertEqual(episode.resolved_at, self.base_time + timedelta(seconds=11))
        self.assertIsNone(self.state().active_episode_id)
        self.assertEqual(self.post(self.reading(11, 27))[0]["outcome"], "duplicate")
        self.assertEqual(len(self.episodes()), 1)
        with Session(self.engine) as session:
            self.assertEqual(
                session.get(Telemetry, episode.opening_telemetry_id).sequence_number, 3
            )
            self.assertEqual(
                session.get(Telemetry, episode.resolving_telemetry_id).sequence_number,
                11,
            )

    def test_strict_high_boundary_and_consecutive_streak(self) -> None:
        self.post(self.reading(1, 30), self.reading(2, 31))
        self.post(self.reading(3, 29), self.reading(4, 31), self.reading(5, 31))
        self.assertEqual(self.state().high_streak, 2)
        self.assertEqual(self.episodes(), [])
        self.post(self.reading(6, 31))
        self.assertEqual(len(self.episodes()), 1)

    def test_alerts_endpoint_lists_persisted_episodes(self) -> None:
        empty = self.client.get("/api/v1/alerts")
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(empty.json()["active_count"], 0)
        self.assertEqual(empty.json()["episodes"], [])
        self.assertEqual(
            empty.json()["rule"],
            {
                "high_threshold": "30",
                "recovery_threshold": "28",
                "consecutive_readings": 3,
                "unit": "celsius",
            },
        )

        self.post(*(self.reading(n, 31 + n) for n in (1, 2, 3)))
        body = self.client.get("/api/v1/alerts").json()
        self.assertEqual(body["active_count"], 1)
        [episode] = body["episodes"]
        self.assertEqual(episode["device_id"], DEVICE_ID)
        self.assertEqual(episode["state"], "active")
        self.assertEqual(episode["opening_value"], "34")
        self.assertIsNone(episode["resolved_at"])
        self.assertIsNone(episode["resolving_value"])

        self.post(*(self.reading(n, 20 + n) for n in (4, 5, 6)))
        body = self.client.get("/api/v1/alerts").json()
        self.assertEqual(body["active_count"], 0)
        [episode] = body["episodes"]
        self.assertEqual(episode["state"], "resolved")
        self.assertEqual(episode["resolving_value"], "26")
        self.assertIsNotNone(episode["resolved_at"])

    def test_concurrent_replay_of_opening_event_creates_one_episode(self) -> None:
        self.post(self.reading(1, 31), self.reading(2, 31))
        third = self.reading(3, 31)
        barrier = Barrier(2)

        def send():
            barrier.wait(timeout=10)
            return self.post(third)[0]["outcome"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (pool.submit(send), pool.submit(send))
            results = [future.result(timeout=15) for future in futures]
        self.assertCountEqual(results, ["accepted", "duplicate"])
        self.assertEqual(len(self.episodes()), 1)
        self.assertEqual(self.state().high_streak, 0)
