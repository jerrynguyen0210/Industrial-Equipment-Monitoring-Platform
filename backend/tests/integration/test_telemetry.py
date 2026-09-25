"""Telemetry acceptance against Alembic-created tables on real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

from alembic import command
from alembic.config import Config
from app.models import Device, Telemetry
from app.seed import DEVICE_ID, GATEWAY_ID
from postgres_test_case import BACKEND, PostgresTestCase
from sqlalchemy import delete, func, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session


def event(**overrides) -> dict:
    # Approved F01, associated with the explicitly seeded device registry.
    return {
        "schema_version": 1,
        "device_id": DEVICE_ID,
        "boot_id": "boot-a",
        "sequence_number": 100,
        "measured_at": datetime(2026, 9, 19, 0, 30, tzinfo=UTC),
        "device_uptime_ms": 534000,
        "gateway_received_at": datetime(2026, 9, 19, 0, 30, 1, tzinfo=UTC),
        "metric": "temperature",
        "value": Decimal("31.4"),
        "unit": "celsius",
        "quality": {"reading": "valid", "clock": "synchronised"},
        **overrides,
    }


class TelemetryPostgresTests(PostgresTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def test_registry_upgrade_and_telemetry_downgrade_preserve_registry(self) -> None:
        self.migrate("downgrade", "0001_registry")
        self.assertNotIn("telemetry", inspect(self.engine).get_table_names())
        self.migrate("upgrade", "head")
        with self.engine.begin() as connection:
            connection.execute(insert(Telemetry).values(**event()))
        self.migrate("downgrade", "0001_registry")
        with Session(self.engine) as session:
            self.assertEqual(session.get(Device, DEVICE_ID).gateway_id, GATEWAY_ID)
        self.migrate("upgrade", "head")
        with self.engine.begin() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes["connection"] = connection
            command.check(config)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(Telemetry)), 0
            )

    def test_duplicate_and_conflicting_identity_leave_original_unchanged(self) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(Telemetry(**event()))
        with Session(self.engine) as session:
            original_received_at = session.scalar(select(Telemetry.backend_received_at))
        for changes in ({}, {"value": Decimal("32.1")}, {"measured_at": None}):
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError) as caught:
                    with self.engine.begin() as connection:
                        connection.execute(insert(Telemetry).values(**event(**changes)))
                self.assertEqual(caught.exception.orig.sqlstate, "23505")
                self.assertEqual(
                    caught.exception.orig.diag.constraint_name, "uq_telemetry_identity"
                )
        with Session(self.engine) as session:
            stored = session.scalars(select(Telemetry)).one()
            for field, expected in event().items():
                self.assertEqual(getattr(stored, field), expected)
            self.assertEqual(stored.backend_received_at, original_received_at)

    def test_concurrent_duplicate_identity_has_one_committed_row(self) -> None:
        barrier = Barrier(2)

        def persist() -> str:
            with self.engine.connect() as connection:
                barrier.wait(timeout=10)
                try:
                    with connection.begin():
                        connection.execute(insert(Telemetry).values(**event()))
                    return "committed"
                except IntegrityError as error:
                    return error.orig.sqlstate

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: persist(), range(2)))
        self.assertCountEqual(results, ["committed", "23505"])
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Telemetry)), 1
            )

    def test_each_identity_component_distinguishes_events(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(Device).values(
                    device_id="other-device", gateway_id=GATEWAY_ID, name="Other"
                )
            )
            for changes in (
                {},
                {"device_id": "other-device"},
                {"boot_id": "boot-b"},
                {"sequence_number": 101},
            ):
                connection.execute(insert(Telemetry).values(**event(**changes)))
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Telemetry)), 4
            )

    def test_null_measurement_and_all_clock_qualities_round_trip(self) -> None:
        for clock in ("synchronised", "unsynchronised", "estimated", "unknown"):
            for measured_at in (None, event()["measured_at"]):
                with self.subTest(clock=clock, measured_at=measured_at):
                    payload = event(
                        boot_id=f"{clock}-{measured_at is None}",
                        measured_at=measured_at,
                        quality={"reading": "valid", "clock": clock},
                    )
                    with Session(self.engine) as session, session.begin():
                        row = Telemetry(**payload)
                        session.add(row)
                        session.flush()
                        session.refresh(row)
                        self.assertEqual(row.measured_at, measured_at)
                        self.assertEqual(row.quality, payload["quality"])

    def test_all_absolute_timestamps_round_trip_in_utc(self) -> None:
        # Fractional offsets cross midnight, exercising date as well as clock time.
        timestamps = {
            "measured_at": datetime.fromisoformat("2026-09-19T00:15:00.123456+09:30"),
            "gateway_received_at": datetime.fromisoformat("2026-09-19T00:15:01-05:00"),
            "backend_received_at": datetime.fromisoformat("2026-09-20T00:15:02+05:45"),
        }
        with self.engine.begin() as connection:
            self.assertEqual(connection.scalar(text("SHOW TIMEZONE")), "UTC")
            connection.execute(text("SET LOCAL TIME ZONE 'Australia/Adelaide'"))
            connection.execute(insert(Telemetry).values(**event(**timestamps)))
        with Session(self.engine) as session, session.begin():
            session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
            stored = session.scalars(select(Telemetry)).one()
            for name, expected in timestamps.items():
                value = getattr(stored, name)
                self.assertEqual(value, expected.astimezone(UTC))
                self.assertEqual(value.utcoffset(), timedelta(0))
        columns = {c["name"]: c for c in inspect(self.engine).get_columns("telemetry")}
        for name in timestamps:
            self.assertTrue(columns[name]["type"].timezone)

    def test_naive_absolute_timestamps_are_rejected(self) -> None:
        for name in ("measured_at", "gateway_received_at", "backend_received_at"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(StatementError, "must include a timezone"):
                    with self.engine.begin() as connection:
                        connection.execute(
                            insert(Telemetry).values(
                                **event(**{name: datetime(2026, 9, 19)})
                            )
                        )

    def test_receipt_default_is_generated_by_postgresql(self) -> None:
        with self.engine.begin() as connection:
            before = connection.scalar(select(func.clock_timestamp()))
            received_at = connection.scalar(
                text(
                    "INSERT INTO telemetry (schema_version, device_id, boot_id, "
                    "sequence_number, device_uptime_ms, gateway_received_at, "
                    "metric, value, unit, quality) VALUES "
                    "(1, :device_id, 'raw-boot', 0, 0, "
                    "TIMESTAMPTZ '2026-09-19T00:30:01Z', 'temperature', 31.4, "
                    '\'celsius\', \'{"reading":"valid","clock":"unknown"}\') '
                    "RETURNING backend_received_at"
                ),
                {"device_id": DEVICE_ID},
            )
            after = connection.scalar(select(func.clock_timestamp()))
            self.assertLessEqual(before, received_at)
            self.assertLessEqual(received_at, after)
            self.assertEqual(received_at.utcoffset(), timedelta(0))

    def test_contract_checks_reject_invalid_storage(self) -> None:
        for changes in (
            {"schema_version": 2},
            {"boot_id": ""},
            {"sequence_number": -1},
            {"device_uptime_ms": -1},
            {"metric": "pressure"},
            {"unit": "fahrenheit"},
            *({"value": Decimal(value)} for value in ("NaN", "Infinity", "-Infinity")),
            {"quality": None},
            {"quality": {}},
            {"quality": []},
            {"quality": {"reading": "valid"}},
            {"quality": {"clock": "unknown"}},
            {"quality": {"reading": "valid", "clock": None}},
            {"quality": {"reading": "invalid", "clock": "unknown"}},
            {"quality": {"reading": "valid", "clock": "invalid"}},
        ):
            with self.subTest(changes=changes):
                self.assert_database_error(
                    insert(Telemetry).values(**event(**changes)), "23514"
                )
        for field in (*event(), "backend_received_at"):
            if field in ("measured_at", "quality"):
                continue
            with self.subTest(required=field):
                self.assert_database_error(
                    insert(Telemetry).values(**event(**{field: None})), "23502"
                )

    def test_device_reference_preserves_history(self) -> None:
        self.assert_database_error(
            insert(Telemetry).values(**event(device_id="missing")), "23503"
        )
        with self.engine.begin() as connection:
            connection.execute(insert(Telemetry).values(**event()))
        self.assert_database_error(
            delete(Device).where(Device.device_id == DEVICE_ID), "23503"
        )

    def test_large_counters_and_decimal_precision_are_preserved(self) -> None:
        payload = event(
            sequence_number=2**63 - 1,
            device_uptime_ms=2**63 - 1,
            value=Decimal("31.41234567890123456789"),
        )
        with self.engine.begin() as connection:
            connection.execute(insert(Telemetry).values(**payload))
        with Session(self.engine) as session:
            stored = session.scalars(select(Telemetry)).one()
            for name in ("sequence_number", "device_uptime_ms", "value"):
                self.assertEqual(getattr(stored, name), payload[name])

    def test_device_time_queries_have_composite_indexes(self) -> None:
        indexes = {i["name"]: i for i in inspect(self.engine).get_indexes("telemetry")}
        for column in ("measured_at", "backend_received_at"):
            self.assertEqual(
                indexes[f"ix_telemetry_device_{column}"]["column_names"],
                ["device_id", column],
            )
        with self.engine.begin() as connection:
            receipt_start = connection.scalar(select(func.clock_timestamp()))
            for number, measured_at in enumerate((event()["measured_at"], None)):
                connection.execute(
                    insert(Telemetry).values(
                        **event(sequence_number=number, measured_at=measured_at)
                    )
                )
        with Session(self.engine) as session:
            history = session.scalars(
                select(Telemetry)
                .where(
                    Telemetry.device_id == DEVICE_ID,
                    Telemetry.measured_at >= event()["measured_at"],
                )
                .order_by(Telemetry.measured_at)
            ).all()
            receipts = session.scalars(
                select(Telemetry)
                .where(
                    Telemetry.device_id == DEVICE_ID,
                    Telemetry.backend_received_at >= receipt_start,
                )
                .order_by(Telemetry.backend_received_at)
            ).all()
            self.assertEqual(len(history), 1)
            self.assertEqual(len(receipts), 2)
