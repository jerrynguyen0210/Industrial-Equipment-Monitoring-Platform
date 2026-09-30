"""Read-only API for persisted temperature alert episodes."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased
from starlette.concurrency import run_in_threadpool

from app.alert_schemas import AlertEpisodeList, AlertEpisodeStatus, AlertRule
from app.alerting import CONSECUTIVE_READINGS, HIGH_THRESHOLD, RECOVERY_THRESHOLD
from app.models import AlertEpisode, Device, Telemetry

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def list_alert_episodes(engine: Engine, limit: int) -> AlertEpisodeList:
    """Return active episodes first, then the most recently opened ones."""
    opening = aliased(Telemetry)
    resolving = aliased(Telemetry)
    statement = (
        select(
            AlertEpisode.id,
            AlertEpisode.device_id,
            Device.name.label("device_name"),
            AlertEpisode.opened_at,
            AlertEpisode.resolved_at,
            opening.value.label("opening_value"),
            resolving.value.label("resolving_value"),
        )
        .join(Device, Device.device_id == AlertEpisode.device_id)
        .join(opening, opening.id == AlertEpisode.opening_telemetry_id)
        .outerjoin(resolving, resolving.id == AlertEpisode.resolving_telemetry_id)
        .order_by(
            AlertEpisode.resolved_at.is_(None).desc(),
            AlertEpisode.opened_at.desc(),
            AlertEpisode.id.desc(),
        )
        .limit(limit)
    )
    active = select(func.count()).where(AlertEpisode.resolved_at.is_(None))

    with Session(engine) as session:
        rows = session.execute(statement).all()
        active_count = session.execute(active).scalar_one()

    return AlertEpisodeList(
        rule=AlertRule(
            high_threshold=HIGH_THRESHOLD,
            recovery_threshold=RECOVERY_THRESHOLD,
            consecutive_readings=CONSECUTIVE_READINGS,
            unit="celsius",
        ),
        active_count=active_count,
        episodes=[
            AlertEpisodeStatus(
                id=row.id,
                device_id=row.device_id,
                device_name=row.device_name,
                state="active" if row.resolved_at is None else "resolved",
                opened_at=row.opened_at,
                opening_value=row.opening_value,
                resolved_at=row.resolved_at,
                resolving_value=row.resolving_value,
            )
            for row in rows
        ],
    )


@router.get("/api/v1/alerts", response_model=AlertEpisodeList)
async def get_alerts(
    request: Request, limit: int = Query(default=20, ge=1, le=100)
) -> AlertEpisodeList:
    """List temperature alert episodes, returning safe dependency errors."""
    try:
        return await run_in_threadpool(
            list_alert_episodes, request.app.state.database_engine, limit
        )
    except SQLAlchemyError:
        logger.warning("alert_episodes_database_failed")
        raise HTTPException(
            status_code=503,
            detail={"reason": "alert_episodes_unavailable"},
        ) from None
