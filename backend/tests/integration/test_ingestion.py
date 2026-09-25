"""HTTP outcomes verified against real PostgreSQL commits and concurrent writes."""

import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from app.main import create_app
from app.models import Device, Gateway, Site, Telemetry
from app.seed import DEVICE_ID, GATEWAY_ID, SITE_ID
from app.telemetry_openapi import VALID_EVENT
from fastapi.testclient import TestClient
from postgres_test_case import PostgresTestCase
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

ENDPOINT = "/api/v1/telemetry/batches"


class IngestionTests(PostgresTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()
        self.token = secrets.token_urlsafe(24)
        self.other_token = secrets.token_urlsafe(24)
        self.unknown_token = secrets.token_urlsafe(24)
        self.enterContext(
            patch.dict(
                os.environ,
                self.environment
                | {
                    "GATEWAY_CREDENTIALS_JSON": json.dumps(
                        {
                            GATEWAY_ID: self.token,
                            "other-gateway": self.other_token,
                            "absent-gateway": self.unknown_token,
                        }
                    )
                },
            )
        )
        with Session(self.engine) as session, session.begin():
            session.add(
                Gateway(gateway_id="other-gateway", site_id=SITE_ID, name="Other")
            )
            session.flush()
            session.add(
                Device(
                    device_id="other-device", gateway_id="other-gateway", name="Other"
                )
            )
        self.client = self.enterContext(
            TestClient(create_app(engine_factory=lambda: self.engine))
        )
        self.reading = VALID_EVENT | {"device_id": DEVICE_ID}

    def post(self, *items: object, token: str | None = None):
        return self.client.post(
            ENDPOINT,
            json={"schema_version": 1, "events": list(items)},
            headers={"Authorization": f"Bearer {token or self.token}"},
        )

    def count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Telemetry))

    def test_valid_event_is_committed_with_server_receipt_time(self) -> None:
        before = datetime.now(UTC)
        response = self.post(self.reading)
        after = datetime.now(UTC)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["results"][0]
        self.assertEqual(result["outcome"], "accepted")
        self.assertNotIn("reason", result)
        with Session(self.engine) as session:
            stored = session.scalars(select(Telemetry)).one()
            self.assertEqual(stored.value, Decimal("31.4"))
            self.assertEqual(
                stored.measured_at.isoformat(), "2026-09-19T00:30:00+00:00"
            )
            self.assertLessEqual(before, stored.backend_received_at)
            self.assertLessEqual(stored.backend_received_at, after)
            self.assertEqual(stored.device_id, DEVICE_ID)

    def test_mixed_batch_has_one_ordered_result_per_item(self) -> None:
        response = self.post(
            self.reading,
            self.reading | {"device_id": "unknown"},
            self.reading | {"device_id": "other-device"},
            self.reading | {"unit": "fahrenheit"},
            None,
            self.reading,
            self.reading | {"value": 99},
            self.reading | {"sequence_number": 101},
        )
        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()["results"]
        self.assertEqual(
            [(item["outcome"], item.get("reason")) for item in results],
            [
                ("accepted", None),
                ("rejected", "unknown_device"),
                ("rejected", "wrong_gateway"),
                ("rejected", "invalid_unit"),
                ("rejected", "malformed_value"),
                ("duplicate", None),
                ("rejected", "identity_conflict"),
                ("accepted", None),
            ],
        )
        self.assertIsNone(results[4]["device_id"])
        self.assertEqual(self.count(), 2)

    def test_matching_retry_preserves_receipts_and_compares_every_immutable_field(
        self,
    ) -> None:
        self.assertEqual(self.post(self.reading).status_code, 200)
        with Session(self.engine) as session:
            original = session.scalars(select(Telemetry)).one()
            receipts = (original.gateway_received_at, original.backend_received_at)
        retry = self.post(
            self.reading
            | {
                "gateway_received_at": "2026-09-20T00:30:01Z",
                "measured_at": "2026-09-19T02:30:00+02:00",
            }
        )
        self.assertEqual(retry.json()["results"][0]["outcome"], "duplicate")
        for change in (
            {"measured_at": None},
            {"device_uptime_ms": 534001},
            {"value": 31.40001},
            {"quality": {"reading": "valid", "clock": "estimated"}},
        ):
            with self.subTest(change=change):
                response = self.post(self.reading | change)
                self.assertEqual(
                    response.json()["results"][0]["reason"], "identity_conflict"
                )
        with Session(self.engine) as session:
            stored = session.scalars(select(Telemetry)).one()
            self.assertEqual(
                (stored.gateway_received_at, stored.backend_received_at), receipts
            )
            self.assertEqual(stored.value, Decimal("31.4"))

    def test_gateway_identity_cannot_be_spoofed_and_disabled_access_is_rejected(
        self,
    ) -> None:
        response = self.post(self.reading, token=self.other_token)
        self.assertEqual(response.json()["results"][0]["reason"], "wrong_gateway")
        response = self.post(self.reading, token=self.unknown_token)
        self.assertEqual(response.status_code, 403)
        for field in ("backend_received_at", "gateway_id", "site_id"):
            response = self.post(self.reading | {field: "injected"})
            self.assertEqual(response.json()["results"][0]["reason"], "malformed_value")
        for model in (Device, Gateway, Site):
            with self.subTest(model=model.__name__):
                with Session(self.engine) as session, session.begin():
                    session.execute(update(model).values(enabled=False))
                response = self.post(self.reading)
                if model is Device:
                    self.assertEqual(
                        response.json()["results"][0]["reason"], "wrong_gateway"
                    )
                else:
                    self.assertEqual(response.status_code, 403)
                with Session(self.engine) as session, session.begin():
                    session.execute(update(model).values(enabled=True))
        self.assertEqual(self.count(), 0)

    def test_batch_limits_and_item_storage_errors_do_not_lose_valid_peers(self) -> None:
        too_many = [self.reading] * 501
        response = self.post(*too_many)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["reason"], "batch_too_large")
        self.assertEqual(self.count(), 0)
        response = self.post(
            *(self.reading | {"sequence_number": n} for n in range(500))
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["results"]), 500)
        self.assertEqual(self.count(), 500)
        body = json.dumps(
            {
                "schema_version": 1,
                "events": [
                    self.reading | {"sequence_number": 600},
                    self.reading
                    | {"sequence_number": 601, "value": "NUMERIC_OVERFLOW"},
                    self.reading | {"device_id": "bad\x00device"},
                    self.reading | {"sequence_number": 602},
                ],
            }
        ).replace('"NUMERIC_OVERFLOW"', "1e200000")
        response = self.client.post(
            ENDPOINT, content=body, headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [r["outcome"] for r in response.json()["results"]],
            ["accepted", "rejected", "rejected", "accepted"],
        )
        self.assertEqual(self.count(), 502)

    def test_precise_numbers_and_null_time_survive_http_to_database(self) -> None:
        number = "31.123456789012345678901234567890123456789"
        body = json.dumps(
            {"schema_version": 1, "events": [self.reading | {"measured_at": None}]}
        ).replace("31.4", number)
        headers = {"Authorization": f"Bearer {self.token}"}
        self.assertEqual(
            self.client.post(ENDPOINT, content=body, headers=headers).status_code, 200
        )
        retry = self.client.post(ENDPOINT, content=body, headers=headers)
        self.assertEqual(retry.json()["results"][0]["outcome"], "duplicate")
        conflict = self.client.post(
            ENDPOINT, content=body.replace(number, number + "1"), headers=headers
        )
        self.assertEqual(conflict.json()["results"][0]["reason"], "identity_conflict")
        with Session(self.engine) as session:
            stored = session.scalars(select(Telemetry)).one()
            self.assertEqual(stored.value, Decimal(number))
            self.assertIsNone(stored.measured_at)

    def test_concurrent_identical_and_conflicting_requests_keep_one_row(self) -> None:
        for index, conflict in enumerate((False, True)):
            barrier = Barrier(2)
            reading = self.reading | {"sequence_number": index}

            def send(value: float, barrier=barrier, reading=reading):
                barrier.wait(timeout=10)
                return self.post(reading | {"value": value})

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(send, value)
                    for value in (31.4, 99 if conflict else 31.4)
                ]
                responses = [future.result(timeout=15) for future in futures]
            for response in responses:
                self.assertEqual(response.status_code, 200, response.text)
            self.assertCountEqual(
                [r.json()["results"][0]["outcome"] for r in responses],
                ["accepted", "rejected" if conflict else "duplicate"],
            )
        self.assertEqual(self.count(), 2)

    def test_failed_commit_returns_no_acceptance_and_rolls_back_whole_batch(
        self,
    ) -> None:
        def fail_commit(session):
            if not session.in_nested_transaction():
                raise OperationalError("COMMIT", {}, Exception("secret-sentinel"))

        event.listen(Session, "before_commit", fail_commit)
        try:
            with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                response = self.post(
                    self.reading, self.reading | {"sequence_number": 101}
                )
        finally:
            event.remove(Session, "before_commit", fail_commit)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("results", response.json())
        self.assertNotIn("secret-sentinel", response.text + " ".join(logs.output))
        self.assertEqual(self.count(), 0)
        self.assertEqual(
            self.post(self.reading).json()["results"][0]["outcome"], "accepted"
        )

    def test_registry_ownership_and_enabled_states_are_locked_until_commit(
        self,
    ) -> None:
        blocked = []

        def attempt_registry_changes(session):
            if session.in_nested_transaction():
                return
            for model in (Device, Gateway, Site):
                with self.assertRaises(OperationalError) as error:
                    with self.engine.begin() as connection:
                        connection.exec_driver_sql("SET LOCAL lock_timeout = '100ms'")
                        connection.execute(update(model).values(enabled=False))
                self.assertEqual(error.exception.orig.sqlstate, "55P03")
                blocked.append(model.__name__)

        event.listen(Session, "before_commit", attempt_registry_changes)
        try:
            response = self.post(self.reading)
        finally:
            event.remove(Session, "before_commit", attempt_registry_changes)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(blocked, ["Device", "Gateway", "Site"])
        self.assertEqual(self.count(), 1)

    def test_commit_succeeds_but_acknowledgement_fails_then_retry_is_duplicate(
        self,
    ) -> None:
        def lose_acknowledgement(session):
            if not session.in_nested_transaction():
                raise OperationalError("COMMIT", {}, Exception("lost acknowledgement"))

        event.listen(Session, "after_commit", lose_acknowledgement)
        try:
            response = self.post(self.reading)
        finally:
            event.remove(Session, "after_commit", lose_acknowledgement)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.count(), 1)
        self.assertEqual(
            self.post(self.reading).json()["results"][0]["outcome"], "duplicate"
        )
