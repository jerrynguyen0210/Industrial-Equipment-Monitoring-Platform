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
        errors = (
            psycopg.OperationalError,
            psycopg.errors.InvalidPassword,
            psycopg.errors.QueryCanceled,
        )
        for path in ("/ready", "/api/health/ready"):
            for error in errors:
                with self.subTest(path=path, error=error.__name__):
                    probe = Mock(side_effect=[None, error("secret-sentinel"), None])
                    with TestClient(create_app(probe)) as client:
                        success = client.get(path)
                        self.assertEqual(success.status_code, 200)
                        self.assertEqual(
                            success.json(), {"status": "ready", "database": "ok"}
                        )
                        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                            failure = client.get(path)
                        self.assertEqual(failure.status_code, 503)
                        self.assertEqual(
                            failure.headers["content-type"], "application/json"
                        )
                        self.assertEqual(
                            failure.json(),
                            {"status": "unavailable", "database": "unavailable"},
                        )
                        self.assertNotIn("secret-sentinel", failure.text)
                        self.assertNotIn("secret-sentinel", " ".join(logs.output))
                        recovered = client.get(path)
                        self.assertEqual(recovered.status_code, 200)
                        self.assertEqual(
                            recovered.json(), {"status": "ready", "database": "ok"}
                        )
                    self.assertEqual(probe.call_count, 3)

    def test_liveness_does_not_depend_on_database(self) -> None:
        probe = Mock(side_effect=psycopg.OperationalError())
        with TestClient(create_app(probe)) as client:
            for path in ("/health", "/api/health/live"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.headers["content-type"], "application/json"
                    )
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
                    for path in ("/ready", "/api/health/ready"):
                        with self.subTest(path=path):
                            response = client.get(path)
                            self.assertEqual(response.status_code, 503)
                            self.assertEqual(
                                response.json(),
                                {"status": "unavailable", "database": "unavailable"},
                            )
                    self.assertEqual(client.get("/health").json(), {"status": "ok"})

    def test_openapi_describes_health_and_readiness_responses(self) -> None:
        with TestClient(create_app(Mock())) as client:
            response = client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        for path in ("/health", "/api/health/live"):
            with self.subTest(path=path):
                responses = schema["paths"][path]["get"]["responses"]
                self.assertEqual(
                    responses["200"]["content"]["application/json"]["schema"]["$ref"],
                    "#/components/schemas/Health",
                )
        for path in ("/ready", "/api/health/ready"):
            for status in ("200", "503"):
                with self.subTest(path=path, status=status):
                    responses = schema["paths"][path]["get"]["responses"]
                    self.assertEqual(
                        responses[status]["content"]["application/json"]["schema"][
                            "$ref"
                        ],
                        "#/components/schemas/Readiness",
                    )
        self.assertEqual(
            schema["components"]["schemas"]["Readiness"]["required"],
            ["status", "database"],
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
