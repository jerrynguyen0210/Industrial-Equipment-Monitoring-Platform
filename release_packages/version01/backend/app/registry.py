"""Ownership checks for callers that have already authenticated a gateway."""

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, Gateway, Site


class OwnershipStatus(StrEnum):
    ALLOWED = "allowed"
    UNKNOWN_DEVICE = "unknown_device"
    WRONG_GATEWAY = "wrong_gateway"
    DISABLED = "disabled"


def check_device_ownership(
    session: Session, *, device_id: str, gateway_id: str
) -> OwnershipStatus:
    """Query committed/transaction-local state using a trusted gateway identifier.

    This is a registry decision, not authentication or a telemetry acknowledgement.
    The eventual ingestion layer owns transaction and HTTP error mapping policy.
    """
    assignment = session.execute(
        select(Device.gateway_id, Device.enabled, Gateway.enabled, Site.enabled)
        .join(Device.gateway)
        .join(Gateway.site)
        .where(Device.device_id == device_id)
    ).one_or_none()
    if assignment is None:
        return OwnershipStatus.UNKNOWN_DEVICE
    if assignment[0] != gateway_id:
        return OwnershipStatus.WRONG_GATEWAY
    if not all(assignment[1:]):
        return OwnershipStatus.DISABLED
    return OwnershipStatus.ALLOWED
