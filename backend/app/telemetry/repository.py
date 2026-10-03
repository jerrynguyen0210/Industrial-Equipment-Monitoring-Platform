"""Telemetry persistence and history queries within caller-owned transactions."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Gateway, Site, Telemetry
from app.telemetry.time import event_time


def lock_gateway_eligibility(session: Session, gateway_id: str) -> Row[Any] | None:
    """Keep gateway/site eligibility stable until the ingestion commit."""
    return session.execute(
        select(Gateway.enabled, Site.enabled)
        .join(Gateway.site)
        .where(Gateway.gateway_id == gateway_id)
        .with_for_update(read=True, of=(Gateway, Site))
    ).one_or_none()


def insert_event(session: Session, values: dict[str, Any]) -> Row[Any] | None:
    """Isolate representation errors and let PostgreSQL enforce event identity."""
    with session.begin_nested():
        return session.execute(
            insert(Telemetry)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_telemetry_identity")
            .returning(Telemetry.id, Telemetry.backend_received_at)
        ).one_or_none()


def read_existing_event(session: Session, identity: dict[str, Any]) -> Telemetry:
    return session.execute(
        select(Telemetry).filter_by(**identity).with_for_update(read=True)
    ).scalar_one()


def read_history_rows(
    session: Session,
    device_id: str,
    range_start: datetime,
    range_end: datetime,
    limit: int,
) -> Sequence[Row[Any]]:
    """Return the newest bounded window; the service restores ascending order."""
    timestamp = event_time(Telemetry)
    return session.execute(
        select(
            Telemetry.id,
            Telemetry.boot_id,
            Telemetry.sequence_number,
            Telemetry.measured_at,
            Telemetry.gateway_received_at,
            Telemetry.quality["clock"].as_string().label("clock_quality"),
            timestamp.label("event_at"),
            Telemetry.value,
            Telemetry.unit,
        )
        .where(
            Telemetry.device_id == device_id,
            timestamp >= range_start,
            timestamp < range_end,
        )
        .order_by(timestamp.desc(), Telemetry.id.desc())
        .limit(limit)
    ).all()
