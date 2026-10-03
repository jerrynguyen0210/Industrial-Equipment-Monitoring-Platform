"""Device registry and status queries; callers own sessions and transactions."""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, func, select, true, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import lateral

from app.db.models import Device, Gateway, Site, Telemetry
from app.telemetry.time import event_time


def list_enabled_gateways(session: Session) -> Sequence[Row[Any]]:
    return session.execute(
        select(Gateway.gateway_id, Gateway.name)
        .join(Gateway.site)
        .where(Gateway.enabled, Gateway.site.has(enabled=True))
        .order_by(Gateway.name, Gateway.gateway_id)
    ).all()


def lock_registration_gateway(session: Session, gateway_id: str) -> Gateway | None:
    return session.execute(
        select(Gateway)
        .where(Gateway.gateway_id == gateway_id)
        .with_for_update(read=True)
    ).scalar_one_or_none()


def lock_device(session: Session, device_id: str) -> Device | None:
    return session.execute(
        select(Device).where(Device.device_id == device_id).with_for_update()
    ).scalar_one_or_none()


def create_device(
    session: Session,
    *,
    device_id: str,
    gateway_id: str,
    name: str,
    password_hash: str,
) -> Device:
    device = Device(
        device_id=device_id,
        gateway_id=gateway_id,
        name=name,
        password_hash=password_hash,
        mqtt_managed=False,
    )
    session.add(device)
    session.flush()
    return device


def delete_device(session: Session, device: Device) -> None:
    session.delete(device)
    session.flush()


def record_presence(
    session: Session, device_id: str, seen_at: datetime | None = None
) -> None:
    """Use database time for ingestion or the explicit heartbeat timestamp."""
    session.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(last_seen_at=seen_at if seen_at is not None else func.clock_timestamp())
    )


def device_exists(session: Session, device_id: str) -> bool:
    return (
        session.execute(
            select(Device.device_id).where(Device.device_id == device_id)
        ).scalar_one_or_none()
        is not None
    )


def lock_assignments(
    session: Session, device_ids: Iterable[str]
) -> dict[str, Row[Any]]:
    """Lock in ID order to serialize presence and alert updates across batches."""
    return {
        row.device_id: row
        for row in session.execute(
            select(Device.device_id, Device.gateway_id, Device.enabled)
            .where(Device.device_id.in_(device_ids))
            .order_by(Device.device_id)
            .with_for_update()
        )
    }


def read_ownership(session: Session, device_id: str) -> Row[Any] | None:
    return session.execute(
        select(Device.gateway_id, Device.enabled, Gateway.enabled, Site.enabled)
        .join(Device.gateway)
        .join(Gateway.site)
        .where(Device.device_id == device_id)
    ).one_or_none()


def list_status_rows(session: Session) -> Sequence[Row[Any]]:
    """Select each device and its newest reading, including devices without data."""
    timestamp = event_time(Telemetry)
    latest = lateral(
        select(
            Telemetry.value,
            Telemetry.unit,
            Telemetry.measured_at,
            Telemetry.gateway_received_at,
            timestamp.label("event_at"),
            Telemetry.quality["clock"].as_string().label("clock_quality"),
        )
        .where(Telemetry.device_id == Device.device_id)
        .order_by(timestamp.desc(), Telemetry.id.desc())
        .limit(1)
    ).alias("latest_reading")
    statement = (
        select(
            Device.device_id,
            Device.name,
            Device.gateway_id,
            Device.enabled,
            Device.last_seen_at,
            Gateway.enabled.label("gateway_enabled"),
            Site.enabled.label("site_enabled"),
            latest.c.value,
            latest.c.unit,
            latest.c.measured_at,
            latest.c.gateway_received_at,
            latest.c.event_at,
            latest.c.clock_quality,
        )
        .select_from(Device)
        .join(Device.gateway)
        .join(Gateway.site)
        .outerjoin(latest, true())
        .order_by(Device.name, Device.device_id)
    )
    return session.execute(statement).all()
