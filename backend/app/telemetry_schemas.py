"""Wire models for the approved telemetry-batch.v1 contract, separate from ORM rows."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

MAX_BATCH_SIZE = 500
MAX_IDENTIFIER_LENGTH = 128
MAX_COUNTER = 2**63 - 1
TIMESTAMP_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

Identifier = Annotated[
    str, Field(strict=True, min_length=1, max_length=MAX_IDENTIFIER_LENGTH)
]
Counter = Annotated[int, Field(strict=True, ge=0, le=MAX_COUNTER)]
ClockQuality = Literal["synchronised", "unsynchronised", "estimated", "unknown"]
ItemReason = Literal[
    "unknown_device",
    "wrong_gateway",
    "invalid_metric",
    "invalid_unit",
    "value_out_of_range",
    "malformed_value",
    "identity_conflict",
]
BatchReason = Literal[
    "unsupported_schema_version", "batch_too_large", "malformed_batch"
]


def require_number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("value must be a finite JSON number")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("value must be a finite JSON number")
    return number


def require_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(TIMESTAMP_PATTERN, value):
        raise ValueError("timestamp must be RFC 3339 with an explicit timezone")
    return value


def normalize_utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError("timestamp must be representable in UTC") from error


Timestamp = Annotated[
    AwareDatetime,
    BeforeValidator(require_timestamp),
    AfterValidator(normalize_utc),
    WithJsonSchema(
        {"type": "string", "format": "date-time", "pattern": TIMESTAMP_PATTERN}
    ),
]
Temperature = Annotated[
    Decimal,
    BeforeValidator(require_number),
    WithJsonSchema({"type": "number"}, mode="validation"),
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelemetryQuality(ContractModel):
    reading: Literal["valid"]
    clock: ClockQuality


class TelemetryEvent(ContractModel):
    """A valid reading; validation alone never establishes acceptance or ownership."""

    device_id: Identifier
    boot_id: Identifier
    sequence_number: Counter
    measured_at: Timestamp | None = Field(
        description=(
            "Required, nullable device measurement time. Only a non-null time with "
            "synchronised clock quality is trustworthy. Other clock qualities "
            "preserve supplied times; receipt times never replace this value."
        )
    )
    device_uptime_ms: Counter
    gateway_received_at: Timestamp
    metric: Literal["temperature"]
    value: Temperature = Field(description="Finite JSON number in degrees Celsius.")
    unit: Literal["celsius"]
    quality: TelemetryQuality


class TelemetryBatch(ContractModel):
    """Fully valid batch schema. HTTP validation must classify items independently."""

    schema_version: Literal[1]
    events: list[TelemetryEvent] = Field(
        strict=True, min_length=1, max_length=MAX_BATCH_SIZE
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        # Python considers True and 1.0 equal to 1; the wire contract does not.
        if type(value) is not int:
            raise ValueError("schema_version must be the integer 1")
        return value


class ValidationDetail(ContractModel):
    loc: list[str | int]
    code: str
    message: str


class TelemetryResponseItem(ContractModel):
    """One result per input item, in input order. Null identity means malformed data."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"outcome": {"const": "rejected"}}},
                    "then": {
                        "required": ["reason"],
                        "properties": {"reason": {"type": "string"}},
                    },
                    "else": {"properties": {"reason": {"type": "null"}}},
                },
                {
                    "if": {
                        "not": {
                            "required": ["reason"],
                            "properties": {"reason": {"const": "malformed_value"}},
                        }
                    },
                    "then": {
                        "properties": {
                            "device_id": {"type": "string"},
                            "boot_id": {"type": "string"},
                            "sequence_number": {"type": "integer"},
                        }
                    },
                },
            ]
        }
    )

    device_id: Identifier | None
    boot_id: Identifier | None
    sequence_number: Counter | None
    outcome: Literal["accepted", "duplicate", "rejected"]
    reason: ItemReason | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "rejected":
            if self.reason is None:
                raise ValueError("rejected outcomes require a reason")
            if (
                None in (self.device_id, self.boot_id, self.sequence_number)
                and self.reason != "malformed_value"
            ):
                raise ValueError("only malformed_value may have an incomplete identity")
        else:
            if self.reason is not None:
                raise ValueError("accepted and duplicate outcomes cannot have a reason")
            if None in (self.device_id, self.boot_id, self.sequence_number):
                raise ValueError("accepted and duplicate outcomes require an identity")
        return self


class TelemetryBatchResponse(ContractModel):
    batch_id: Identifier
    results: list[TelemetryResponseItem] = Field(
        min_length=1, max_length=MAX_BATCH_SIZE
    )


class TelemetryBatchError(ContractModel):
    reason: BatchReason
    message: str
    details: list[ValidationDetail] = Field(default_factory=list)
