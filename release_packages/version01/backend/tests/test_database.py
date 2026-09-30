"""Protect the configuration boundary between libpq and SQLAlchemy."""

import os
import unittest
from unittest.mock import patch

from app.database import create_database_engine


class DatabaseEngineTests(unittest.TestCase):
    def test_url_preserves_special_password_and_ssl_settings(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "DATABASE_URL": (
                        "postgresql://local:p%25%40ss%3Aword@db:5433/registry"
                        "?sslmode=require&application_name=registry"
                        "&options=-c%20timezone%3DAustralia%2FAdelaide"
                    ),
                    "PGHOST": "wrong-host",
                },
            ),
            patch("app.database.create_engine") as create,
        ):
            create_database_engine()
        args, kwargs = create.call_args
        self.assertEqual(args, ("postgresql+psycopg://",))
        settings = kwargs["connect_args"]
        self.assertEqual(settings["password"], "p%@ss:word")
        self.assertEqual(settings["host"], "db")
        self.assertEqual(settings["port"], "5433")
        self.assertEqual(settings["dbname"], "registry")
        self.assertEqual(settings["sslmode"], "require")
        self.assertEqual(settings["application_name"], "registry")
        self.assertEqual(settings["connect_timeout"], "3")
        self.assertTrue(
            settings["options"].startswith("-c timezone=Australia/Adelaide ")
        )
        self.assertTrue(settings["options"].endswith("-c timezone=UTC"))

    def test_pg_settings_preserve_unescaped_password(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "PGHOST": "localhost",
                    "PGPORT": "5432",
                    "PGDATABASE": "registry",
                    "PGUSER": "local",
                    "PGPASSWORD": "spaces @ : % ' and \\",
                },
                clear=True,
            ),
            patch("app.database.create_engine") as create,
        ):
            create_database_engine()
        settings = create.call_args.kwargs["connect_args"]
        self.assertEqual(settings["password"], "spaces @ : % ' and \\")
