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
    gateway_received_at: datetime
    event_at: datetime
    timestamp_source: Literal["measured_at", "gateway_received_at"]
    clock_quality: Literal["synchronised", "unsynchronised", "estimated", "unknown"]


class DeviceStatus(BaseModel):
    device_id: str
    name: str
    gateway_id: str
    enabled: bool
    online: bool
    last_seen_at: datetime | None
    latest_reading: LatestReading | None


class DeviceStatusList(BaseModel):
    devices: list[DeviceStatus]


class GatewayOption(BaseModel):
    gateway_id: str
    name: str


class GatewayList(BaseModel):
    gateways: list[GatewayOption]
