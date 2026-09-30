"""Bounded, event-time telemetry history response models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    event_at: datetime
    timestamp_source: Literal["measured_at", "gateway_received_at"]
    measured_at: datetime | None
    gateway_received_at: datetime
    clock_quality: Literal["synchronised", "unsynchronised", "estimated", "unknown"]
    value: Decimal
    unit: str
    gap_before: bool


class DeviceHistory(BaseModel):
    device_id: str
    unit: str
    range_start: datetime
    range_end: datetime
    truncated: bool
    points: list[HistoryPoint]
