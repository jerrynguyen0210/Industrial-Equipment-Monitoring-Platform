"""Two-stage telemetry validation for an eventual authenticated HTTP adapter."""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import HTTPException, Request
from pydantic import Field, TypeAdapter, ValidationError

from app.telemetry_schemas import (
    MAX_BATCH_SIZE,
    Counter,
    Identifier,
    ItemReason,
    TelemetryBatch,
    TelemetryBatchError,
    TelemetryEvent,
    TelemetryResponseItem,
    ValidationDetail,
)


class _BatchEnvelope(TelemetryBatch):
    # Keep individual malformed values for classification instead of failing the
    # whole mixed batch through FastAPI's automatic nested-model validation.
    events: list[Any] = Field(strict=True, min_length=1, max_length=MAX_BATCH_SIZE)


@dataclass(frozen=True)
class ValidatedTelemetryBatch:
    schema_version: Literal[1]
    items: tuple[TelemetryEvent | TelemetryResponseItem, ...]


class BatchValidationError(ValueError):
    def __init__(self, error: TelemetryBatchError) -> None:
        super().__init__(error.message)
        self.error = error


def _reject_constant(value: str) -> None:
    raise ValueError("Non-standard JSON constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _validation_details(error: ValidationError) -> list[ValidationDetail]:
    # Never serialize Pydantic's input/ctx values: they can echo entire payloads,
    # non-finite numbers or exception objects into a response.
    return [
        ValidationDetail(loc=list(item["loc"]), code=item["type"], message=item["msg"])
        for item in error.errors(include_input=False, include_context=False)
    ]


def _identity(value: object, adapter: TypeAdapter) -> Any:
    try:
        return adapter.validate_python(value)
    except ValidationError:
        return None


_identifier = TypeAdapter(Identifier)
_counter = TypeAdapter(Counter)


def validate_telemetry_item(payload: Any) -> TelemetryEvent | TelemetryResponseItem:
    """Return valid data or a permanent rejection, never an accepted claim."""
    try:
        return TelemetryEvent.model_validate(payload)
    except ValidationError as error:
        errors = error.errors(include_input=False, include_context=False)
        fields = {item["loc"][0] if item["loc"] else None for item in errors}
        reason: ItemReason = "malformed_value"
        # Structural errors take precedence; metric then unit break remaining ties.
        if fields <= {"metric", "unit"} and all(
            item["type"] == "literal_error" for item in errors
        ):
            reason = "invalid_metric" if "metric" in fields else "invalid_unit"
        raw = payload if isinstance(payload, dict) else {}
        return TelemetryResponseItem(
            device_id=_identity(raw.get("device_id"), _identifier),
            boot_id=_identity(raw.get("boot_id"), _identifier),
            sequence_number=_identity(raw.get("sequence_number"), _counter),
            outcome="rejected",
            reason=reason,
        )


def parse_telemetry_batch(body: bytes | str) -> ValidatedTelemetryBatch:
    """Decode decimal numbers losslessly, validate envelope, then each item in order."""
    try:
        payload = json.loads(
            body.decode("utf-8") if isinstance(body, bytes) else body,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, UnicodeError, RecursionError, InvalidOperation) as error:
        raise BatchValidationError(
            TelemetryBatchError(
                reason="malformed_batch",
                message="Body must be UTF-8 JSON with unique object members.",
            )
        ) from error

    try:
        envelope = _BatchEnvelope.model_validate(payload)
    except ValidationError as error:
        details = _validation_details(error)
        reason = "malformed_batch"
        message = (
            "Expected schema_version and an events array containing 1 to 500 items."
        )
        # Fixed precedence: malformed envelope, unsupported version, oversized batch.
        structural_errors = [
            item
            for item in details
            if not (
                item.loc == ["schema_version"]
                and item.code == "literal_error"
                or item.loc == ["events"]
                and item.code == "too_long"
            )
        ]
        if not structural_errors:
            if any(item.loc == ["schema_version"] for item in details):
                reason = "unsupported_schema_version"
                message = "Only schema_version 1 is supported."
            else:
                reason = "batch_too_large"
                message = "A batch may contain at most 500 events."
        raise BatchValidationError(
            TelemetryBatchError(reason=reason, message=message, details=details)
        ) from error

    return ValidatedTelemetryBatch(
        schema_version=envelope.schema_version,
        items=tuple(validate_telemetry_item(item) for item in envelope.events),
    )


async def read_telemetry_batch(request: Request) -> ValidatedTelemetryBatch:
    """Use after authentication; map request errors to HTTP 400, retaining item errors.

    Do not call request.json() first: its float conversion loses decimal precision.
    No route is mounted until authentication and durable ingestion are implemented.
    """
    try:
        return parse_telemetry_batch(await request.body())
    except BatchValidationError as error:
        raise HTTPException(status_code=400, detail=error.error.model_dump()) from error
