"""Isolated PostgreSQL databases shared by the persistence acceptance suites."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from app.config import database_conninfo
from app.database import create_database_engine
from app.seed import seed_registry
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[2]


class PostgresTestCase(unittest.TestCase):
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
        cls.database_name = "iemp_backend_test_" + uuid4().hex
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
