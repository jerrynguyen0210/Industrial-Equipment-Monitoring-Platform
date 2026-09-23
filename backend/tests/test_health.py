import os
import socket
import unittest
from unittest.mock import Mock, patch

import psycopg
from app.main import create_app
from fastapi.testclient import TestClient


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "PGHOST": "localhost",
                "PGPORT": "5432",
                "PGDATABASE": "test",
                "PGUSER": "test",
                "PGPASSWORD": "test-only",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_readiness_checks_database_and_reports_recovery(self) -> None:
        probe = Mock(side_effect=[None, psycopg.OperationalError("secret"), None])
        with TestClient(create_app(probe)) as client:
            self.assertEqual(client.get("/api/health/ready").status_code, 200)
            failure = client.get("/api/health/ready")
            self.assertEqual(failure.status_code, 503)
            self.assertEqual(
                failure.json(), {"status": "unavailable", "database": "unavailable"}
            )
            self.assertNotIn("secret", failure.text)
            self.assertEqual(
                client.get("/api/health/ready").json(),
                {"status": "ready", "database": "ok"},
            )

    def test_liveness_does_not_depend_on_database(self) -> None:
        probe = Mock(side_effect=psycopg.OperationalError())
        with TestClient(create_app(probe)) as client:
            response = client.get("/api/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        probe.assert_not_called()

    def test_real_database_connection_failure_returns_unavailable(self) -> None:
        # Reserve a local port without listening so no unrelated service is used.
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            with patch.dict(
                os.environ,
                {"PGHOST": "127.0.0.1", "PGPORT": str(unavailable.getsockname()[1])},
            ):
                with TestClient(create_app()) as client:
                    response = client.get("/api/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(), {"status": "unavailable", "database": "unavailable"}
        )

    def test_missing_configuration_fails_startup(self) -> None:
        with patch.dict(os.environ, {"PGPASSWORD": ""}):
            with self.assertRaisesRegex(RuntimeError, "PGPASSWORD"):
                with TestClient(create_app(Mock())):
                    pass

    def test_invalid_port_fails_startup(self) -> None:
        with patch.dict(os.environ, {"PGPORT": "70000"}):
            with self.assertRaisesRegex(RuntimeError, "PGPORT"):
                with TestClient(create_app(Mock())):
                    pass


if __name__ == "__main__":
    unittest.main()
