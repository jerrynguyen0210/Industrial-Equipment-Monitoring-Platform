"""Generate the standalone ingestion contract; this does not mount an HTTP route."""

import argparse
import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from app.telemetry_schemas import (
    TelemetryBatch,
    TelemetryBatchError,
    TelemetryBatchResponse,
)

VALID_EVENT = {
    "device_id": "motor-001",
    "boot_id": "boot-a",
    "sequence_number": 100,
    "measured_at": "2026-09-19T00:30:00Z",
    "device_uptime_ms": 534000,
    "gateway_received_at": "2026-09-19T00:30:01Z",
    "metric": "temperature",
    "value": 31.4,
    "unit": "celsius",
    "quality": {"reading": "valid", "clock": "synchronised"},
}
REQUEST_EXAMPLES = {
    "valid": {
        "summary": "F01: valid temperature reading",
        "value": {"schema_version": 1, "events": [VALID_EVENT]},
    },
    "unknown_clock": {
        "summary": "Explicitly null measurement time with unknown clock quality",
        "value": {
            "schema_version": 1,
            "events": [
                {
                    **VALID_EVENT,
                    "measured_at": None,
                    "quality": {"reading": "valid", "clock": "unknown"},
                }
            ],
        },
    },
    "mixed": {
        "summary": "F05: new events, matching retry, and an invalid unit",
        "description": "Assumes committed F01; validate each item independently.",
        "value": {
            "schema_version": 1,
            "events": [
                {**VALID_EVENT, "sequence_number": 101},
                VALID_EVENT,
                {**VALID_EVENT, "sequence_number": 102, "unit": "fahrenheit"},
                {**VALID_EVENT, "sequence_number": 103},
            ],
        },
    },
}
MIXED_RESPONSE = {
    "batch_id": "01K5EXAMPLE",
    "results": [
        {
            "device_id": "motor-001",
            "boot_id": "boot-a",
            "sequence_number": sequence,
            "outcome": outcome,
            **({"reason": "invalid_unit"} if outcome == "rejected" else {}),
        }
        for sequence, outcome in (
            (101, "accepted"),
            (100, "duplicate"),
            (102, "rejected"),
            (103, "accepted"),
        )
    ],
}


UNSUPPORTED_VERSION_ERROR = {
    "detail": {
        "reason": "unsupported_schema_version",
        "message": "Only schema_version 1 is supported.",
        "details": [
            {
                "loc": ["schema_version"],
                "code": "literal_error",
                "message": "Input should be 1",
            }
        ],
    }
}


def _ref(model: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{model}"}


def build_telemetry_openapi() -> dict:
    _, schema = models_json_schema(
        [
            (TelemetryBatch, "validation"),
            (TelemetryBatchResponse, "serialization"),
            (TelemetryBatchError, "serialization"),
        ],
        ref_template="#/components/schemas/{model}",
    )
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Telemetry ingestion contract",
            "version": "telemetry-batch.v1",
            "description": (
                "Contract for the future ingestion endpoint. Models and validation "
                "are implemented; authentication, persistence orchestration and this "
                "route are not yet installed in the running application."
            ),
        },
        "paths": {
            "/api/v1/telemetry/batches": {
                "post": {
                    "operationId": "ingestTelemetryBatch",
                    "summary": "Ingest a version 1 telemetry batch",
                    "description": (
                        "Authenticate first, validate the envelope, then classify each "
                        "item independently. Invalid items do not block valid ones. "
                        "One result per item in input order; accepted requires a "
                        "durable database commit. Unknown identity fields on bad items "
                        "are null. Structural item errors take precedence over metric, "
                        "then unit errors."
                    ),
                    "x-implementation-status": "models-and-validation-only",
                    "security": [{"GatewayCredential": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": _ref("TelemetryBatch"),
                                "examples": REQUEST_EXAMPLES,
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Processing and commit succeeded",
                            "content": {
                                "application/json": {
                                    "schema": _ref("TelemetryBatchResponse"),
                                    "examples": {"mixed": {"value": MIXED_RESPONSE}},
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid envelope; no item processing",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["detail"],
                                        "properties": {
                                            "detail": _ref("TelemetryBatchError")
                                        },
                                    },
                                    "examples": {
                                        "unsupported_version": {
                                            "value": UNSUPPORTED_VERSION_ERROR
                                        }
                                    },
                                }
                            },
                        },
                        "401": {"description": "Missing or invalid gateway credential"},
                        "403": {"description": "Gateway credential is not authorized"},
                        "429": {
                            "description": "Transient failure; keep queued and retry"
                        },
                        "5XX": {
                            "description": (
                                "Transient server/commit failure; no accepted claims"
                            )
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": schema["$defs"],
            "securitySchemes": {
                "GatewayCredential": {"type": "http", "scheme": "bearer"}
            },
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(build_telemetry_openapi(), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
