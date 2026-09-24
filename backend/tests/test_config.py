import os
import traceback
import unittest
from unittest.mock import Mock, patch

from app.config import database_conninfo
from app.main import check_database, create_app
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict


class DatabaseConfigurationTests(unittest.TestCase):
    def test_url_overrides_pg_settings_and_decodes_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://local:p%40ss%3Aword@db:5433/telemetry",
                "PGHOST": "wrong-host",
                "PGPASSWORD": "wrong-password",
                "PGPORT": "invalid",
            },
        ):
            settings = conninfo_to_dict(database_conninfo())
        self.assertEqual(settings["host"], "db")
        self.assertEqual(settings["port"], "5433")
        self.assertEqual(settings["dbname"], "telemetry")
        self.assertEqual(settings["user"], "local")
        self.assertEqual(settings["password"], "p@ss:word")

    def test_url_without_port_uses_5432(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgres://local:test-only@db/telemetry",
                "PGPORT": "9999",
            },
        ):
            self.assertEqual(conninfo_to_dict(database_conninfo())["port"], "5432")

    def test_url_alone_is_sufficient_for_startup(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://local:test-only@db/telemetry"},
            clear=True,
        ):
            with TestClient(create_app(Mock())) as client:
                self.assertEqual(client.get("/api/health/live").status_code, 200)

    def test_invalid_urls_fail_startup_without_disclosing_values(self) -> None:
        urls = [
            "https://local:secret-sentinel@db/telemetry",
            "postgresql://local:secret-sentinel@db/telemetry?secret-sentinel=bad",
            "postgresql://local:secret-sentinel@db:70000/telemetry",
            "postgresql://local:secret-sentinel@db:invalid/telemetry",
            "postgresql://local:secret-sentinel@db/",
            "postgresql://local@db/telemetry",
        ]
        for index, url in enumerate(urls):
            with self.subTest(url_type=index):
                with patch.dict(os.environ, {"DATABASE_URL": url}):
                    try:
                        with TestClient(create_app(Mock())):
                            self.fail("Invalid URL did not fail startup")
                    except RuntimeError as error:
                        self.assertIn("DATABASE_URL", str(error))
                        self.assertNotIn(
                            "secret-sentinel",
                            "".join(traceback.format_exception(error)),
                        )

    def test_database_probe_uses_url_and_bounded_timeouts(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://local:test-only@db:5433/telemetry"},
        ):
            with patch("app.main.psycopg.connect") as connect:
                check_database()
        args, kwargs = connect.call_args
        self.assertEqual(conninfo_to_dict(args[0])["host"], "db")
        self.assertEqual(kwargs["connect_timeout"], 3)
        self.assertEqual(kwargs["options"], "-c statement_timeout=2000")
        connect.return_value.__enter__.return_value.execute.assert_called_once_with(
            "SELECT 1"
        )
