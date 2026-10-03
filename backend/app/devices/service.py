"""Device business rules and transaction coordination."""

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.devices import repository
from app.devices.credentials import hash_password, verify_password
from app.devices.schemas import (
    DeviceRegistration,
    DeviceStatus,
    DeviceStatusList,
    GatewayList,
    GatewayOption,
    LatestReading,
)
from app.integrations.mqtt import BrokerAdmin, BrokerUnavailable

logger = logging.getLogger("uvicorn.error")
ONLINE_WINDOW = timedelta(seconds=90)


class GatewayNotFoundError(Exception):
    """The registration gateway is absent or disabled."""


class DeviceNotFoundError(Exception):
    """The device is not registered."""


class InvalidDeviceCredentialsError(Exception):
    """The supplied credentials do not authorize this operation."""


class NameRequiredError(Exception):
    """The name is empty after trimming whitespace."""


def list_gateways(engine: Engine) -> GatewayList:
    with Session(engine) as session:
        rows = repository.list_enabled_gateways(session)
    return GatewayList(
        gateways=[GatewayOption.model_validate(row._mapping) for row in rows]
    )


def register_device(
    engine: Engine, broker: BrokerAdmin, registration: DeviceRegistration
) -> DeviceStatus:
    broker_created = False
    try:
        with Session(engine) as session, session.begin():
            gateway = repository.lock_registration_gateway(
                session, registration.gateway_id
            )
            if gateway is None or not gateway.enabled or not gateway.site.enabled:
                raise GatewayNotFoundError
            name = registration.name.strip()
            if not name:
                raise NameRequiredError
            device = repository.create_device(
                session,
                device_id=registration.device_id,
                gateway_id=registration.gateway_id,
                name=name,
                password_hash=hash_password(registration.password),
            )
            broker_created = broker.create_device(
                registration.device_id, registration.password
            )
            device.mqtt_managed = broker_created
    except Exception:
        if broker_created:
            try:
                broker.delete_device(registration.device_id)
            except BrokerUnavailable:
                logger.warning("device_registration_broker_rollback_failed")
        raise
    return DeviceStatus(
        device_id=registration.device_id,
        gateway_id=registration.gateway_id,
        name=registration.name.strip(),
        enabled=True,
        online=False,
        last_seen_at=None,
        latest_reading=None,
    )


def remove_device(engine: Engine, broker: BrokerAdmin, device_id: str) -> None:
    """Remove an unused registration; foreign keys preserve recorded history."""
    broker_disabled = False
    try:
        with Session(engine) as session, session.begin():
            device = repository.lock_device(session, device_id)
            if device is None:
                raise DeviceNotFoundError
            managed = device.mqtt_managed
            repository.delete_device(session, device)
            if managed:
                broker_disabled = broker.disable_device(device_id)
    except Exception:
        if broker_disabled:
            try:
                broker.enable_device(device_id)
            except BrokerUnavailable:
                logger.warning("device_delete_broker_rollback_failed")
        raise
    if broker_disabled:
        try:
            broker.delete_device(device_id)
        except BrokerUnavailable:
            # A disabled orphan cannot connect; a later registration clears it.
            logger.warning("device_delete_broker_cleanup_failed")


def configure_existing_mqtt(
    engine: Engine, broker: BrokerAdmin, device_id: str, password: str
) -> None:
    with Session(engine) as session, session.begin():
        device = repository.lock_device(session, device_id)
        if device is None or not verify_password(password, device.password_hash):
            raise InvalidDeviceCredentialsError
        device.mqtt_managed = broker.ensure_device(device_id, password)


def record_heartbeat(engine: Engine, device_id: str, password: str) -> None:
    with Session(engine) as session, session.begin():
        device = repository.lock_device(session, device_id)
        if (
            device is None
            or not device.enabled
            or not device.gateway.enabled
            or not device.gateway.site.enabled
            or not verify_password(password, device.password_hash)
        ):
            raise InvalidDeviceCredentialsError
        repository.record_presence(session, device_id, datetime.now(UTC))


def list_device_status(engine: Engine) -> DeviceStatusList:
    """Return every registered device and its newest reading by event time."""
    with Session(engine) as session:
        rows = repository.list_status_rows(session)

    now = datetime.now(UTC)
    return DeviceStatusList(
        devices=[
            DeviceStatus(
                device_id=row.device_id,
                name=row.name,
                gateway_id=row.gateway_id,
                enabled=row.enabled,
                online=(
                    row.enabled
                    and row.gateway_enabled
                    and row.site_enabled
                    and row.last_seen_at is not None
                    and now - ONLINE_WINDOW <= row.last_seen_at <= now
                ),
                last_seen_at=row.last_seen_at,
                latest_reading=(
                    LatestReading(
                        value=row.value,
                        unit=row.unit,
                        measured_at=row.measured_at,
                        gateway_received_at=row.gateway_received_at,
                        event_at=row.event_at,
                        timestamp_source=(
                            "measured_at"
                            if row.measured_at is not None
                            and row.clock_quality == "synchronised"
                            else "gateway_received_at"
                        ),
                        clock_quality=row.clock_quality,
                    )
                    if row.value is not None
                    else None
                ),
            )
            for row in rows
        ]
    )


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
    assignment = repository.read_ownership(session, device_id)
    if assignment is None:
        return OwnershipStatus.UNKNOWN_DEVICE
    if assignment[0] != gateway_id:
        return OwnershipStatus.WRONG_GATEWAY
    if not all(assignment[1:]):
        return OwnershipStatus.DISABLED
    return OwnershipStatus.ALLOWED
