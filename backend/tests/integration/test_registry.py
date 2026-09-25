"""Real PostgreSQL acceptance tests; all writes target a newly created database.

REGISTRY_TEST_DATABASE_URL identifies a PostgreSQL maintenance database whose
role may CREATE DATABASE. It is never used as a migration or seed target.
"""

import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from app.config import database_conninfo
from app.database import create_database_engine
from app.models import Device, Gateway, Site
from app.registry import OwnershipStatus, check_device_ownership
from app.seed import DEVICE_ID, GATEWAY_ID, SITE_ID, SeedConflictError, seed_registry
from psycopg import sql
from sqlalchemy import func, insert, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[2]


class RegistryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_url = os.environ.get("REGISTRY_TEST_DATABASE_URL")
        if not test_url:
            raise RuntimeError(
                "Set REGISTRY_TEST_DATABASE_URL to a PostgreSQL test server; "
                "its role must be able to CREATE DATABASE"
            )
        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            admin_conninfo = database_conninfo()
        cls.admin = psycopg.connect(
            admin_conninfo,
            autocommit=True,
            connect_timeout=3,
            options="-c statement_timeout=10000",
        )
        cls.addClassCleanup(cls.admin.close)
        cls.database_name = "iemp_registry_test_" + uuid4().hex
        cls.admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(cls.database_name)
            )
        )
        cls.addClassCleanup(cls.drop_database)
        cls.environment = {
            **os.environ,
            "DATABASE_URL": make_url(test_url)
            .set(database=cls.database_name)
            .render_as_string(hide_password=False),
        }
        with patch.dict(os.environ, cls.environment):
            cls.engine = create_database_engine()
        cls.addClassCleanup(cls.engine.dispose)

    @classmethod
    def drop_database(cls) -> None:
        # Only this suite's freshly generated database can ever be dropped.
        cls.admin.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(cls.database_name)
            )
        )

    def migrate(self, direction: str, revision: str) -> None:
        with self.engine.begin() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes["connection"] = connection
            getattr(command, direction)(config, revision)

    def setUp(self) -> None:
        self.migrate("upgrade", "head")
        self.addCleanup(self.migrate, "downgrade", "base")

    def seed(self) -> None:
        with Session(self.engine) as session, session.begin():
            seed_registry(session)

    def assert_database_error(self, statement, sqlstate: str) -> None:
        with self.assertRaises(IntegrityError) as caught:
            with self.engine.begin() as connection:
                connection.execute(statement)
        self.assertEqual(caught.exception.orig.sqlstate, sqlstate)

    def test_migration_up_down_up_and_model_agreement(self) -> None:
        self.seed()
        self.migrate("downgrade", "base")
        self.assertEqual(inspect(self.engine).get_table_names(), ["alembic_version"])
        self.migrate("upgrade", "head")
        with self.engine.begin() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes["connection"] = connection
            command.check(config)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(Device)), 0
            )
        self.seed()
        with Session(self.engine) as session:
            device = session.get(Device, DEVICE_ID)
            self.assertEqual(device.gateway.site.site_id, SITE_ID)
            self.assertEqual(device.gateway.devices, [device])

    def test_duplicate_device_id_rejected_within_and_across_gateways(self) -> None:
        self.seed()
        with self.engine.begin() as connection:
            connection.execute(
                insert(Gateway).values(
                    gateway_id="other-gateway", site_id=SITE_ID, name="Other gateway"
                )
            )
        for gateway_id in (GATEWAY_ID, "other-gateway"):
            with self.subTest(gateway_id=gateway_id):
                self.assert_database_error(
                    insert(Device).values(
                        device_id=DEVICE_ID, gateway_id=gateway_id, name="Duplicate"
                    ),
                    "23505",
                )
        with Session(self.engine) as session:
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Device)), 1
            )
            self.assertEqual(session.get(Device, DEVICE_ID).gateway_id, GATEWAY_ID)

    def test_concurrent_duplicate_registration_has_one_winner(self) -> None:
        self.seed()
        barrier = Barrier(2)

        def register() -> str:
            with self.engine.connect() as connection:
                barrier.wait(timeout=10)
                try:
                    with connection.begin():
                        connection.execute(
                            insert(Device).values(
                                device_id="concurrent-device",
                                gateway_id=GATEWAY_ID,
                                name="Concurrent device",
                            )
                        )
                    return "committed"
                except IntegrityError as error:
                    return error.orig.sqlstate

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: register(), range(2)))
        self.assertCountEqual(results, ["committed", "23505"])
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Device, "concurrent-device"))

    def test_foreign_keys_reject_orphans_and_parent_deletion(self) -> None:
        self.seed()
        statements = [
            insert(Gateway).values(
                gateway_id="orphan", site_id="missing", name="Orphan"
            ),
            insert(Device).values(
                device_id="orphan", gateway_id="missing", name="Orphan"
            ),
            text("DELETE FROM gateways WHERE gateway_id = 'gateway-demo-001'"),
            text("DELETE FROM sites WHERE site_id = 'site-demo-001'"),
        ]
        for statement in statements:
            with self.subTest(statement=str(statement)):
                self.assert_database_error(statement, "23503")
        with self.assertRaises(IntegrityError):
            with Session(self.engine) as session, session.begin():
                gateway = session.get(Gateway, GATEWAY_ID)
                self.assertEqual(len(gateway.devices), 1)
                session.delete(gateway)

    def test_database_defaults_and_required_values(self) -> None:
        # Raw SQL proves defaults are enforced by PostgreSQL, independently of ORM.
        with self.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO sites (site_id, name) VALUES ('s', 'S')")
            )
            connection.execute(
                text(
                    "INSERT INTO gateways (gateway_id, site_id, name) "
                    "VALUES ('g', 's', 'G')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO devices (device_id, gateway_id, name) "
                    "VALUES ('d', 'g', 'D')"
                )
            )
        with Session(self.engine) as session:
            self.assertTrue(session.get(Site, "s").enabled)
            self.assertTrue(session.get(Gateway, "g").enabled)
            self.assertTrue(session.get(Device, "d").enabled)
        for table, identifier in (
            ("sites", "site_id"),
            ("gateways", "gateway_id"),
            ("devices", "device_id"),
        ):
            with self.subTest(table=table):
                self.assert_database_error(
                    text(f"UPDATE {table} SET enabled = NULL"), "23502"
                )
                self.assert_database_error(
                    text(f"UPDATE {table} SET name = NULL"), "23502"
                )
                self.assert_database_error(
                    text(f"UPDATE {table} SET {identifier} = ''"), "23514"
                )
        self.assert_database_error(
            text("UPDATE devices SET gateway_id = NULL"), "23502"
        )
        self.assert_database_error(text("UPDATE gateways SET site_id = NULL"), "23502")

    def test_ownership_and_each_disabled_level(self) -> None:
        self.seed()
        with Session(self.engine) as session, session.begin():

            def check(device: str, gateway: str) -> OwnershipStatus:
                return check_device_ownership(
                    session, device_id=device, gateway_id=gateway
                )

            self.assertEqual(check(DEVICE_ID, GATEWAY_ID), OwnershipStatus.ALLOWED)
            self.assertEqual(
                check("missing", GATEWAY_ID), OwnershipStatus.UNKNOWN_DEVICE
            )
            self.assertEqual(check(DEVICE_ID, "other"), OwnershipStatus.WRONG_GATEWAY)
            for model in (Device, Gateway, Site):
                with self.subTest(model=model.__name__):
                    session.execute(update(model).values(enabled=False))
                    self.assertEqual(
                        check(DEVICE_ID, GATEWAY_ID), OwnershipStatus.DISABLED
                    )
                    session.execute(update(model).values(enabled=True))
                    self.assertEqual(
                        check(DEVICE_ID, GATEWAY_ID), OwnershipStatus.ALLOWED
                    )

    def test_repeat_seed_preserves_names_and_disabled_state(self) -> None:
        self.seed()
        with self.engine.begin() as connection:
            for model in (Site, Gateway, Device):
                connection.execute(update(model).values(name="Edited", enabled=False))
        self.seed()
        with Session(self.engine) as session:
            for model in (Site, Gateway, Device):
                rows = session.scalars(select(model)).all()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].name, "Edited")
                self.assertFalse(rows[0].enabled)

    def test_gateway_seed_conflict_rolls_back_new_site(self) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(
                Gateway(
                    gateway_id=GATEWAY_ID,
                    name="Existing gateway",
                    site=Site(site_id="existing-site", name="Existing site"),
                )
            )
        with self.assertRaisesRegex(SeedConflictError, "different site"):
            self.seed()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Site, SITE_ID))
            self.assertIsNone(session.get(Device, DEVICE_ID))
            self.assertEqual(session.get(Gateway, GATEWAY_ID).site_id, "existing-site")

    def test_device_seed_conflict_rolls_back_new_parents(self) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(
                Device(
                    device_id=DEVICE_ID,
                    name="Existing device",
                    gateway=Gateway(
                        gateway_id="existing-gateway",
                        name="Existing gateway",
                        site=Site(site_id="existing-site", name="Existing site"),
                    ),
                )
            )
        with self.assertRaisesRegex(SeedConflictError, "different gateway"):
            self.seed()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Site, SITE_ID))
            self.assertIsNone(session.get(Gateway, GATEWAY_ID))
            self.assertEqual(
                session.get(Device, DEVICE_ID).gateway_id, "existing-gateway"
            )

    def test_concurrent_seed_runs_create_one_hierarchy(self) -> None:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: self.seed(), range(2)))
        with Session(self.engine) as session:
            for model in (Site, Gateway, Device):
                self.assertEqual(
                    session.scalar(select(func.count()).select_from(model)), 1
                )

    def test_cli_upgrade_downgrade_and_repeatable_seed(self) -> None:
        # Exercise env.py's normal engine path and the actual seed entry point.
        commands = [
            ["alembic", "downgrade", "base"],
            ["alembic", "upgrade", "head"],
            ["app.seed"],
            ["app.seed"],
            ["alembic", "check"],
        ]
        for args in commands:
            result = subprocess.run(
                [sys.executable, "-m", *args],
                cwd=BACKEND,
                env=self.environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        with Session(self.engine) as session:
            self.assertEqual(
                session.get(Device, DEVICE_ID).gateway.site.site_id, SITE_ID
            )


if __name__ == "__main__":
    unittest.main()
