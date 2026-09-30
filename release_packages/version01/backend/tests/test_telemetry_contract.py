import json
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from unittest.mock import patch

from app.telemetry_openapi import (
    MIXED_RESPONSE,
    REQUEST_EXAMPLES,
    VALID_EVENT,
    build_telemetry_openapi,
)
from app.telemetry_schemas import (
    MAX_COUNTER,
    TelemetryBatch,
    TelemetryBatchResponse,
    TelemetryEvent,
    TelemetryResponseItem,
)
from app.telemetry_validation import (
    BatchValidationError,
    ValidatedTelemetryBatch,
    parse_telemetry_batch,
    read_telemetry_batch,
    validate_telemetry_item,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


def batch_json(events: list | None = None, **changes: object) -> str:
    return json.dumps(
        {"schema_version": 1, "events": events if events is not None else [VALID_EVENT]}
        | changes
    )


class TelemetryModelTests(unittest.TestCase):
    def test_normative_event_and_zero_counters(self) -> None:
        for value in (0, -12.5, 31.4):
            with self.subTest(value=value):
                event = TelemetryEvent.model_validate(
                    VALID_EVENT
                    | {"value": value, "sequence_number": 0, "device_uptime_ms": 0}
                )
                self.assertEqual(event.value, Decimal(str(value)))
                self.assertEqual(
                    event.measured_at, datetime(2026, 9, 19, 0, 30, tzinfo=UTC)
                )
                self.assertEqual(event.boot_id, "boot-a")

    def test_nullable_measurement_is_required_and_preserved_for_each_clock(
        self,
    ) -> None:
        for clock in ("synchronised", "unsynchronised", "estimated", "unknown"):
            for measured_at in (None, VALID_EVENT["measured_at"]):
                with self.subTest(clock=clock, measured_at=measured_at):
                    event = TelemetryEvent.model_validate(
                        VALID_EVENT
                        | {
                            "measured_at": measured_at,
                            "quality": {"reading": "valid", "clock": clock},
                        }
                    )
                    self.assertEqual(event.measured_at is None, measured_at is None)
                    self.assertEqual(event.quality.clock, clock)
        missing = deepcopy(VALID_EVENT)
        del missing["measured_at"]
        with self.assertRaises(ValidationError):
            TelemetryEvent.model_validate(missing)

    def test_timestamps_require_timezone_and_normalize_offsets(self) -> None:
        for field in ("measured_at", "gateway_received_at"):
            for invalid in (
                "2026-09-19T00:30:00",
                "2026-09-19",
                1789777800,
                True,
                "2026-09-19 00:30:00Z",
                "2026-02-30T00:30:00Z",
                datetime(2026, 9, 19),
                "0001-01-01T00:00:00+09:30",
            ):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(ValidationError):
                        TelemetryEvent.model_validate(VALID_EVENT | {field: invalid})
            event = TelemetryEvent.model_validate(
                VALID_EVENT | {field: "2026-09-19T00:15:00.123456+09:30"}
            )
            self.assertEqual(
                getattr(event, field),
                datetime(2026, 9, 18, 14, 45, 0, 123456, tzinfo=UTC),
            )

    def test_invalid_types_values_fields_and_quality(self) -> None:
        cases = [
            ("value", value)
            for value in (
                None,
                "31.4",
                True,
                [],
                {},
                float("nan"),
                float("inf"),
                float("-inf"),
                Decimal("NaN"),
                Decimal("Infinity"),
            )
        ]
        for field in ("sequence_number", "device_uptime_ms"):
            cases.extend(
                (field, value) for value in (-1, 1.5, 1.0, "1", True, MAX_COUNTER + 1)
            )
        for field in ("device_id", "boot_id"):
            cases.extend((field, value) for value in (None, "", 123, "x" * 129))
        cases.extend(
            [
                ("metric", "humidity"),
                ("unit", "fahrenheit"),
                ("gateway_received_at", None),
                ("backend_received_at", "2026-09-19T00:30:02Z"),
                ("site_id", "untrusted-site"),
                ("schema_version", 1),
                ("quality", None),
                ("quality", {}),
                ("quality", {"reading": "invalid", "clock": "unknown"}),
                ("quality", {"reading": "valid", "clock": "synchronized"}),
                ("quality", {"reading": "valid", "clock": "unknown", "extra": True}),
            ]
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    TelemetryEvent.model_validate(VALID_EVENT | {field: value})
        for field in VALID_EVENT:
            payload = deepcopy(VALID_EVENT)
            del payload[field]
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                TelemetryEvent.model_validate(payload)

    def test_version_and_batch_models_do_not_coerce(self) -> None:
        for version in (None, True, 1.0, "1", 2):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                TelemetryBatch.model_validate(
                    {"schema_version": version, "events": [VALID_EVENT]}
                )
        for events in (None, {}, (), [], [VALID_EVENT] * 501):
            with (
                self.subTest(events_type=type(events)),
                self.assertRaises(ValidationError),
            ):
                TelemetryBatch.model_validate({"schema_version": 1, "events": events})

    def test_response_outcomes_and_reason_invariants(self) -> None:
        identity = {
            "device_id": "motor-001",
            "boot_id": "boot-a",
            "sequence_number": 100,
        }
        for outcome in ("accepted", "duplicate"):
            item = TelemetryResponseItem(**identity, outcome=outcome)
            self.assertNotIn("reason", item.model_dump(exclude_none=True))
            for invalid in ({"reason": "invalid_unit"}, {"device_id": None}):
                with (
                    self.subTest(outcome=outcome, invalid=invalid),
                    self.assertRaises(ValidationError),
                ):
                    TelemetryResponseItem.model_validate(
                        identity | {"outcome": outcome} | invalid
                    )
        for reason in (
            "unknown_device",
            "wrong_gateway",
            "invalid_metric",
            "invalid_unit",
            "value_out_of_range",
            "malformed_value",
            "identity_conflict",
        ):
            self.assertEqual(
                TelemetryResponseItem(
                    **identity, outcome="rejected", reason=reason
                ).reason,
                reason,
            )
        for invalid in (
            {"outcome": "rejected"},
            {"outcome": "rejected", "reason": "unsupported_schema_version"},
            {"outcome": "rejected", "reason": "invalid_unit", "device_id": None},
            {"outcome": "queued"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                TelemetryResponseItem.model_validate(identity | invalid)


class TelemetryBoundaryTests(unittest.TestCase):
    def test_envelope_errors_prevent_item_processing(self) -> None:
        cases = [
            ("{", "malformed_batch"),
            ("null", "malformed_batch"),
            ("[]", "malformed_batch"),
            ("{}", "malformed_batch"),
            (batch_json([]), "malformed_batch"),
            (batch_json(events="wrong"), "malformed_batch"),
            (batch_json(schema_version=2), "unsupported_schema_version"),
            (batch_json(schema_version="1"), "malformed_batch"),
            (batch_json(schema_version=True), "malformed_batch"),
            (batch_json(schema_version=1.0), "malformed_batch"),
            (batch_json([VALID_EVENT] * 501), "batch_too_large"),
            (
                batch_json([VALID_EVENT] * 501, schema_version=2),
                "unsupported_schema_version",
            ),
            (batch_json([], schema_version=2), "malformed_batch"),
            (batch_json(extra="secret-sentinel"), "malformed_batch"),
            ('{"schema_version":1,"schema_version":2,"events":[]}', "malformed_batch"),
            (batch_json().replace("31.4", "NaN"), "malformed_batch"),
            (batch_json().replace("31.4", "Infinity"), "malformed_batch"),
            (
                batch_json().replace("31.4", "1e999999999999999999999"),
                "malformed_batch",
            ),
            (b"\xff", "malformed_batch"),
        ]
        for body, reason in cases:
            with self.subTest(reason=reason, body=str(body)[:60]):
                with patch(
                    "app.telemetry_validation.validate_telemetry_item"
                ) as validate:
                    with self.assertRaises(BatchValidationError) as caught:
                        parse_telemetry_batch(body)
                validate.assert_not_called()
                self.assertEqual(caught.exception.error.reason, reason)
                self.assertNotIn(
                    "secret-sentinel", caught.exception.error.model_dump_json()
                )

    def test_one_and_five_hundred_item_boundaries(self) -> None:
        for count in (1, 500):
            parsed = parse_telemetry_batch(batch_json([VALID_EVENT] * count))
            self.assertEqual(len(parsed.items), count)
            self.assertTrue(
                all(isinstance(item, TelemetryEvent) for item in parsed.items)
            )

    def test_mixed_items_preserve_order_and_never_claim_acceptance(self) -> None:
        parsed = parse_telemetry_batch(json.dumps(REQUEST_EXAMPLES["mixed"]["value"]))
        self.assertEqual(
            [item.sequence_number for item in parsed.items], [101, 100, 102, 103]
        )
        self.assertIsInstance(parsed.items[0], TelemetryEvent)
        self.assertIsInstance(parsed.items[1], TelemetryEvent)
        self.assertEqual(parsed.items[2].outcome, "rejected")
        self.assertEqual(parsed.items[2].reason, "invalid_unit")
        self.assertIsInstance(parsed.items[3], TelemetryEvent)

    def test_reason_precedence_and_malformed_identity(self) -> None:
        cases = [
            (VALID_EVENT | {"metric": "pressure"}, "invalid_metric"),
            (
                VALID_EVENT | {"metric": "pressure", "unit": "fahrenheit"},
                "invalid_metric",
            ),
            (VALID_EVENT | {"unit": "fahrenheit", "value": "bad"}, "malformed_value"),
            (VALID_EVENT | {"value": True}, "malformed_value"),
            (VALID_EVENT | {"value": "NaN"}, "malformed_value"),
            (VALID_EVENT | {"sequence_number": True}, "malformed_value"),
            (
                {key: value for key, value in VALID_EVENT.items() if key != "unit"},
                "malformed_value",
            ),
            (None, "malformed_value"),
            ([], "malformed_value"),
            ({}, "malformed_value"),
        ]
        for payload, reason in cases:
            with self.subTest(payload=payload):
                item = validate_telemetry_item(payload)
                self.assertEqual(item.outcome, "rejected")
                self.assertEqual(item.reason, reason)
                json.dumps(item.model_dump(), allow_nan=False)
        invalid = validate_telemetry_item(VALID_EVENT | {"sequence_number": True})
        self.assertIsNone(invalid.sequence_number)
        self.assertEqual(invalid.device_id, "motor-001")

    def test_numeric_precision_is_preserved_before_model_validation(self) -> None:
        number = "31.123456789012345678901234567890123456789"
        body = (
            batch_json()
            .replace("31.4", number)
            .replace('"sequence_number": 100', f'"sequence_number": {MAX_COUNTER}')
        )
        item = parse_telemetry_batch(body.encode()).items[0]
        self.assertEqual(item.value, Decimal(number))
        self.assertEqual(item.sequence_number, MAX_COUNTER)

    def test_http_dependency_reports_400_and_retains_item_failures(self) -> None:
        application = FastAPI()

        @application.post("/validate")
        def validate(
            batch: Annotated[ValidatedTelemetryBatch, Depends(read_telemetry_batch)],
        ):
            # Validation harness only: deliberately makes no durability claims.
            return {
                "valid": sum(isinstance(item, TelemetryEvent) for item in batch.items),
                "rejected": [
                    item.model_dump()
                    for item in batch.items
                    if isinstance(item, TelemetryResponseItem)
                ],
            }

        with TestClient(application) as client:
            response = client.post("/validate", content=batch_json(schema_version=2))
            self.assertEqual(response.status_code, 400)
            detail = response.json()["detail"]
            self.assertEqual(detail["reason"], "unsupported_schema_version")
            self.assertEqual(detail["details"][0]["loc"], ["schema_version"])
            mixed = client.post("/validate", json=REQUEST_EXAMPLES["mixed"]["value"])
            self.assertEqual(mixed.status_code, 200)
            self.assertEqual(mixed.json()["valid"], 3)
            self.assertEqual(mixed.json()["rejected"][0]["reason"], "invalid_unit")
            invalid = client.post(
                "/validate", content=batch_json().replace("31.4", "NaN")
            )
            self.assertEqual(invalid.status_code, 400)


class TelemetryOpenAPITests(unittest.TestCase):
    def test_examples_match_models_and_expected_classification(self) -> None:
        for name in ("valid", "unknown_clock"):
            TelemetryBatch.model_validate(REQUEST_EXAMPLES[name]["value"])
        TelemetryBatchResponse.model_validate(MIXED_RESPONSE)
        document = build_telemetry_openapi()
        schemas = document["components"]["schemas"]
        event = schemas["TelemetryEvent"]
        self.assertIn("measured_at", event["required"])
        self.assertFalse(event["additionalProperties"])
        self.assertEqual(event["properties"]["value"]["type"], "number")
        self.assertEqual(event["properties"]["metric"]["const"], "temperature")
        self.assertEqual(event["properties"]["unit"]["const"], "celsius")
        self.assertEqual(
            schemas["TelemetryBatch"]["properties"]["events"]["maxItems"], 500
        )
        self.assertIn("allOf", schemas["TelemetryResponseItem"])

        def check_references(value: object) -> None:
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertIn(
                        value["$ref"].removeprefix("#/components/schemas/"), schemas
                    )
                for child in value.values():
                    check_references(child)
            elif isinstance(value, list):
                for child in value:
                    check_references(child)

        check_references(document)

    def test_committed_openapi_matches_generated_contract(self) -> None:
        path = Path(__file__).resolve().parents[2] / "docs" / "telemetry-openapi.json"
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8")), build_telemetry_openapi()
        )


if __name__ == "__main__":
    unittest.main()
