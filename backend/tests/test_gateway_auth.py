import json
import os
import secrets
import unittest
from unittest.mock import Mock, patch

from app.gateway_auth import load_gateway_credentials
from app.main import create_app
from app.telemetry_openapi import build_telemetry_openapi
from fastapi.testclient import TestClient


class GatewayAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = secrets.token_urlsafe(24)
        environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://test:test-only@localhost/test",
                "GATEWAY_CREDENTIALS_JSON": json.dumps({"gateway-test": self.token}),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.engine = Mock()
        self.client = self.enterContext(
            TestClient(create_app(engine_factory=lambda: self.engine))
        )

    def test_invalid_credentials_fail_before_body_or_database_processing(self) -> None:
        headers = [
            {},
            {"Authorization": "Bearer invalid", "X-Gateway-ID": "gateway-test"},
            {"Authorization": f"Basic {self.token}"},
            {"Authorization": f"Bearer {self.token} trailing"},
            [("Authorization", f"Bearer {self.token}"), ("Authorization", "Bearer x")],
        ]
        for header in headers:
            with self.subTest(headers=bool(header)):
                response = self.client.post(
                    "/api/v1/telemetry/batches", content="not JSON", headers=header
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
                self.assertNotIn(self.token, response.text)
        self.engine.connect.assert_not_called()

    def test_valid_credential_reaches_envelope_validation_without_database(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/telemetry/batches",
            content="{}",
            headers={"Authorization": f"bEaReR {self.token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["reason"], "malformed_batch")
        self.engine.connect.assert_not_called()

    def test_configuration_rejects_ambiguous_or_invalid_credentials_safely(
        self,
    ) -> None:
        for value in (
            "not-json",
            "[]",
            '{"a":"secret-sentinel","a":"other"}',
            '{"a":"same","b":"same"}',
            '{"":"secret-sentinel"}',
            '{"a":42}',
            '{"a":""}',
            '{"a":"contains whitespace"}',
            '{"a":"replace-with-provisioned-credential"}',
        ):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"GATEWAY_CREDENTIALS_JSON": value}),
            ):
                with self.assertRaises(RuntimeError) as error:
                    load_gateway_credentials()
                self.assertNotIn("secret-sentinel", str(error.exception))
        with patch.dict(os.environ, {"GATEWAY_CREDENTIALS_JSON": ""}):
            self.assertEqual(load_gateway_credentials(), {})

    def test_running_openapi_matches_implemented_contract(self) -> None:
        live = self.client.get("/openapi.json").json()
        contract = build_telemetry_openapi()
        self.assertEqual(
            live["paths"]["/api/v1/telemetry/batches"],
            contract["paths"]["/api/v1/telemetry/batches"],
        )
        for name, schema in contract["components"]["schemas"].items():
            self.assertEqual(live["components"]["schemas"][name], schema)
