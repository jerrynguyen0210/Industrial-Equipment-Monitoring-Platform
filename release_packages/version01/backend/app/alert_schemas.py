"""Read-only temperature alert response models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AlertRule(BaseModel):
    high_threshold: Decimal
    recovery_threshold: Decimal
    consecutive_readings: int
    unit: Literal["celsius"]


class AlertEpisodeStatus(BaseModel):
    id: int
    device_id: str
    device_name: str
    state: Literal["active", "resolved"]
    opened_at: datetime
    opening_value: Decimal
    resolved_at: datetime | None
    resolving_value: Decimal | None


class AlertEpisodeList(BaseModel):
    rule: AlertRule
    active_count: int
    episodes: list[AlertEpisodeStatus]
