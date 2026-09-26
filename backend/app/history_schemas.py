"""Bounded, measurement-time telemetry history response models."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    measured_at: datetime
    value: Decimal
    gap_before: bool


class DeviceHistory(BaseModel):
    device_id: str
    unit: str
    range_start: datetime
    range_end: datetime
    truncated: bool
    points: list[HistoryPoint]
