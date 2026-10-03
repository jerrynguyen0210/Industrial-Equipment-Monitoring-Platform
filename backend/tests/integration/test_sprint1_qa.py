"""S1-QA-01..10 telemetry decisions exercised through the API and PostgreSQL."""

import json
import os
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.db.models import AlertEpisode, AlertState, Telemetry
from app.db.seed import DEVICE_ID, GATEWAY_ID
from app.main import create_app
from app.telemetry.openapi import VALID_EVENT
from fastapi.testclient import TestClient
from postgres_test_case import PostgresTestCase
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

ENDPOINT = "/api/v1/telemetry/batches"


class SprintOneTelemetryQATests(PostgresTestCase):
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
        self.reading = VALID_EVENT | {"device_id": DEVICE_ID}

    def post(self, *events: object, schema_version: int = 1):
        return self.client.post(
            ENDPOINT,
            json={"schema_version": schema_version, "events": list(events)},
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def assert_outcomes(self, response, events: tuple, expected: list[tuple]) -> None:
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body.get("batch_id"), "Committed batch needs a batch_id")
        results = body["results"]
        self.assertEqual(
            len(results), len(events), "Every input needs one ordered result"
        )
        self.assertEqual(
            [(item["outcome"], item.get("reason")) for item in results],
            expected,
            "Per-item outcome/reason violates the telemetry contract",
        )
        for index, (event, item) in enumerate(zip(events, results, strict=True)):
            if not isinstance(event, dict):
                continue
            self.assertEqual(
                (item["device_id"], item["boot_id"], item["sequence_number"]),
                (event["device_id"], event["boot_id"], event["sequence_number"]),
                f"Result {index} lost its input identity",
            )

    def rows(self) -> list[Telemetry]:
        with Session(self.engine) as session:
            return list(session.scalars(select(Telemetry).order_by(Telemetry.id)))

    def fresh(self, boot: str, sequence: int, seconds: int, value: int) -> dict:
        at = self.base_time + timedelta(seconds=seconds)
        return self.reading | {
            "boot_id": boot,
            "sequence_number": sequence,
            "device_uptime_ms": sequence * 1000,
            "measured_at": at.isoformat(),
            "gateway_received_at": at.isoformat(),
            "value": value,
        }

    def latest(self) -> dict:
        response = self.client.get("/api/v1/devices")
        self.assertEqual(response.status_code, 200, response.text)
        return next(
            device["latest_reading"]
            for device in response.json()["devices"]
            if device["device_id"] == DEVICE_ID
        )

    def test_s1_qa_01_valid_event_persists_every_contract_field(self) -> None:
        """S1-QA-01: a valid simulator event commits all identity/time fields."""
        with self.engine.connect() as connection:
            before = connection.scalar(select(func.clock_timestamp()))
        events = (self.reading,)
        self.assert_outcomes(self.post(*events), events, [("accepted", None)])
        with self.engine.connect() as connection:
            after = connection.scalar(select(func.clock_timestamp()))
        (stored,) = self.rows()
        for field in (
            "device_id",
            "boot_id",
            "sequence_number",
            "device_uptime_ms",
            "metric",
            "unit",
            "quality",
        ):
            self.assertEqual(getattr(stored, field), self.reading[field], field)
        self.assertEqual(stored.schema_version, 1)
        self.assertEqual(stored.value, Decimal("31.4"))
        for field in ("measured_at", "gateway_received_at"):
            self.assertEqual(
                getattr(stored, field), datetime.fromisoformat(self.reading[field])
            )
            self.assertEqual(getattr(stored, field).utcoffset(), timedelta(0))
        self.assertLessEqual(before, stored.backend_received_at)
        self.assertLessEqual(stored.backend_received_at, after)
        self.assertEqual(stored.backend_received_at.utcoffset(), timedelta(0))

    def test_s1_qa_02_ten_identical_submissions_store_one_row(self) -> None:
        """S1-QA-02: first submission accepts; nine retries are duplicates."""
        events = (self.reading,)
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                outcome = "accepted" if attempt == 0 else "duplicate"
                self.assert_outcomes(self.post(*events), events, [(outcome, None)])
        self.assertEqual(len(self.rows()), 1, "Retries inserted another row")

    def test_s1_qa_03_identity_conflict_logs_and_preserves_original(self) -> None:
        """S1-QA-03: changed immutable content rejects without mutation."""
        events = (self.reading,)
        self.assert_outcomes(self.post(*events), events, [("accepted", None)])
        original = self.rows()[0]
        original_fields = {
            column.name: getattr(original, column.name)
            for column in Telemetry.__table__.columns
        }
        changed = self.reading | {"value": 99}
        with patch("app.telemetry.service.logger.info") as conflict_log:
            response = self.post(changed)
        self.assert_outcomes(response, (changed,), [("rejected", "identity_conflict")])
        conflict_log.assert_called_once_with(
            "telemetry_identity_conflict",
            extra={"batch_id": response.json()["batch_id"], "item_index": 0},
        )
        (stored,) = self.rows()
        self.assertEqual(
            {
                column.name: getattr(stored, column.name)
                for column in Telemetry.__table__.columns
            },
            original_fields,
            "Identity conflict changed the committed original",
        )

    def test_s1_qa_04_mixed_batch_is_ordered_and_partially_committed(self) -> None:
        """S1-QA-04: valid peers survive duplicate and invalid neighbors."""
        self.assert_outcomes(
            self.post(self.reading), (self.reading,), [("accepted", None)]
        )
        events = (
            self.reading | {"sequence_number": 101},
            self.reading,
            self.reading | {"value": 99},
            self.reading | {"sequence_number": 102, "unit": "fahrenheit"},
            self.reading | {"sequence_number": 103, "value": "NaN"},
            self.reading | {"device_id": "qa-unregistered-device"},
            self.reading | {"sequence_number": 104},
        )
        self.assert_outcomes(
            self.post(*events),
            events,
            [
                ("accepted", None),
                ("duplicate", None),
                ("rejected", "identity_conflict"),
                ("rejected", "invalid_unit"),
                ("rejected", "malformed_value"),
                ("rejected", "unknown_device"),
                ("accepted", None),
            ],
        )
        self.assertEqual(
            [(row.sequence_number, row.value) for row in self.rows()],
            [(100, Decimal("31.4")), (101, Decimal("31.4")), (104, Decimal("31.4"))],
            "Rejected mixed-batch items were stored or valid peers were lost",
        )

    def test_s1_qa_05_lost_commit_acknowledgement_retries_safely(self) -> None:
        """S1-QA-05: an uncertain response after commit is safe to retry."""
        events = (self.reading, self.reading | {"sequence_number": 101})

        def lose_acknowledgement(session):
            if not session.in_nested_transaction():
                raise OperationalError("COMMIT", {}, Exception("lost acknowledgement"))

        sqlalchemy_event.listen(Session, "after_commit", lose_acknowledgement)
        try:
            with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                response = self.post(*events)
        finally:
            sqlalchemy_event.remove(Session, "after_commit", lose_acknowledgement)
        self.assertTrue(
            any("telemetry_database_failed" in line for line in logs.output),
            "Commit acknowledgement failure was not logged",
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["reason"], "ingestion_unavailable")
        self.assertNotIn(
            "results", response.json(), "Uncertain commit was acknowledged"
        )
        self.assertEqual(len(self.rows()), 2, "The simulated commit did not persist")
        self.assert_outcomes(
            self.post(*events), events, [("duplicate", None), ("duplicate", None)]
        )
        self.assertEqual(len(self.rows()), 2, "Retry created additional rows")

    def test_s1_qa_06_invalid_version_unit_value_and_device_have_codes(self) -> None:
        """S1-QA-06: unsupported envelope and invalid items have stable reasons."""
        response = self.post(self.reading, schema_version=2)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(
            response.json()["detail"]["reason"], "unsupported_schema_version"
        )
        self.assertEqual(len(self.rows()), 0, "Invalid envelope reached persistence")
        events = (
            self.reading | {"unit": "fahrenheit"},
            self.reading | {"value": "31.4"},
            self.reading | {"device_id": "qa-unregistered-device"},
        )
        self.assert_outcomes(
            self.post(*events),
            events,
            [
                ("rejected", "invalid_unit"),
                ("rejected", "malformed_value"),
                ("rejected", "unknown_device"),
            ],
        )
        self.assertEqual(len(self.rows()), 0, "Rejected items reached persistence")

    def test_s1_qa_07_unsynchronised_null_measurement_stays_null(self) -> None:
        """S1-QA-07: unknown measurement time is accepted without fabrication."""
        event = self.reading | {
            "measured_at": None,
            "quality": {"reading": "valid", "clock": "unsynchronised"},
        }
        self.assert_outcomes(self.post(event), (event,), [("accepted", None)])
        (stored,) = self.rows()
        self.assertIsNone(stored.measured_at, "Backend fabricated measurement time")
        self.assertEqual(stored.quality, event["quality"])
        self.assertEqual(
            stored.gateway_received_at,
            datetime.fromisoformat(event["gateway_received_at"]),
        )

    def test_s1_qa_08_older_same_boot_reading_cannot_replace_current(self) -> None:
        """S1-QA-08: older event time is historical, not current/live state."""
        with self.engine.connect() as connection:
            self.base_time = connection.scalar(
                select(func.clock_timestamp())
            ) - timedelta(minutes=1)
        newer = self.fresh("boot-a", 12, 20, 31)
        older = self.fresh("boot-a", 10, 10, 27)
        self.assert_outcomes(self.post(newer), (newer,), [("accepted", None)])
        self.assert_outcomes(self.post(older), (older,), [("accepted", None)])
        self.assertEqual(len(self.rows()), 2, "Historical reading was discarded")
        self.assertEqual(self.latest()["value"], "31")
        self.assertEqual(
            datetime.fromisoformat(self.latest()["event_at"]),
            datetime.fromisoformat(newer["measured_at"]),
            "Older reading replaced current reading",
        )
        with Session(self.engine) as session:
            state = session.get(AlertState, DEVICE_ID)
            self.assertEqual(state.high_streak, 1, "Older reading advanced live alert")
            self.assertEqual(
                state.last_event_at, datetime.fromisoformat(newer["measured_at"])
            )

    def test_s1_qa_09_old_boot_replay_cannot_replace_new_boot_state(self) -> None:
        """S1-QA-09: an older event from a prior boot remains historical."""
        with self.engine.connect() as connection:
            self.base_time = connection.scalar(
                select(func.clock_timestamp())
            ) - timedelta(minutes=1)
        old_boot = self.fresh("boot-old", 1, 10, 31)
        new_boot = self.fresh("boot-new", 1, 20, 31)
        replay = self.fresh("boot-old", 2, 15, 27)
        for event in (old_boot, new_boot, replay):
            self.assert_outcomes(self.post(event), (event,), [("accepted", None)])
        self.assertEqual(len(self.rows()), 3, "Cross-boot replay was not stored")
        self.assertEqual(self.latest()["value"], "31")
        self.assertEqual(
            datetime.fromisoformat(self.latest()["event_at"]),
            datetime.fromisoformat(new_boot["measured_at"]),
            "Old-boot replay replaced new-boot current reading",
        )
        with Session(self.engine) as session:
            state = session.get(AlertState, DEVICE_ID)
            self.assertEqual(state.high_streak, 2, "Old-boot replay reset live state")
            self.assertEqual(
                state.last_event_at, datetime.fromisoformat(new_boot["measured_at"])
            )
        next_reading = self.fresh("boot-new", 2, 30, 31)
        self.assert_outcomes(
            self.post(next_reading), (next_reading,), [("accepted", None)]
        )
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(AlertEpisode)), 1
            )

    def test_s1_qa_10_database_defines_three_part_unique_identity(self) -> None:
        """S1-QA-10: PostgreSQL enforces the exact event identity tuple."""
        constraints = {
            constraint["name"]: constraint["column_names"]
            for constraint in inspect(self.engine).get_unique_constraints("telemetry")
        }
        self.assertEqual(
            constraints.get("uq_telemetry_identity"),
            ["device_id", "boot_id", "sequence_number"],
            "Database lacks the approved three-part unique identity",
        )
        first = self.reading | {"sequence_number": 1, "boot_id": "boot-a"}
        second = first | {"boot_id": "boot-b"}
        self.assert_outcomes(self.post(first), (first,), [("accepted", None)])
        self.assert_outcomes(self.post(second), (second,), [("accepted", None)])
        self.assertEqual(len(self.rows()), 2, "New boot reused the old identity")
