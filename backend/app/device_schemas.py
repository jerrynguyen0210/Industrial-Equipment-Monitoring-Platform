"""Read-only equipment status response models."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LatestReading(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: Decimal
    unit: str
    measured_at: datetime | None
    clock_quality: Literal["synchronised", "unsynchronised", "estimated", "unknown"]


class DeviceStatus(BaseModel):
    device_id: str
    name: str
    latest_reading: LatestReading | None


class DeviceStatusList(BaseModel):
    devices: list[DeviceStatus]
