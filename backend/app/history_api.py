"""Read-only, bounded temperature history ordered by trustworthy measurement time."""

import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.history_schemas import DeviceHistory, HistoryPoint
from app.models import Device, Telemetry

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

MAX_POINTS = 2000
MAX_RANGE = timedelta(days=7)
MAX_CONNECTED_GAP = timedelta(minutes=2)


class DeviceNotFoundError(Exception):
    """The requested device is not registered."""


def read_device_history(
    engine: Engine, device_id: str, range_start: datetime, range_end: datetime
) -> DeviceHistory:
    with Session(engine) as session:
        exists = session.execute(
            select(Device.device_id).where(Device.device_id == device_id)
        ).scalar_one_or_none()
        if exists is None:
            raise DeviceNotFoundError

        # Select the newest bounded window, then restore measurement-time order.
        rows = session.execute(
            select(
                Telemetry.id,
                Telemetry.boot_id,
                Telemetry.sequence_number,
                Telemetry.measured_at,
                Telemetry.value,
            )
            .where(
                Telemetry.device_id == device_id,
                Telemetry.measured_at >= range_start,
                Telemetry.measured_at < range_end,
                Telemetry.quality["clock"].as_string() == "synchronised",
            )
            .order_by(Telemetry.measured_at.desc(), Telemetry.id.desc())
            .limit(MAX_POINTS + 1)
        ).all()

    truncated = len(rows) > MAX_POINTS
    ordered = list(reversed(rows[:MAX_POINTS]))
    points: list[HistoryPoint] = []
    previous = None
    for row in ordered:
        gap_before = (
            previous is None
            or row.boot_id != previous.boot_id
            or row.sequence_number != previous.sequence_number + 1
            or row.measured_at - previous.measured_at > MAX_CONNECTED_GAP
        )
        points.append(
            HistoryPoint(
                measured_at=row.measured_at,
                value=row.value,
                gap_before=gap_before,
            )
        )
        previous = row

    return DeviceHistory(
        device_id=device_id,
        unit="celsius",
        range_start=range_start,
        range_end=range_end,
        truncated=truncated,
        points=points,
    )


@router.get(
    "/api/v1/devices/{device_id}/telemetry/history", response_model=DeviceHistory
)
async def get_device_history(
    request: Request,
    device_id: str,
    range_start: Annotated[datetime, Query(alias="from")],
    range_end: Annotated[datetime, Query(alias="to")],
) -> DeviceHistory:
    if (
        range_start.tzinfo is None
        or range_end.tzinfo is None
        or range_start >= range_end
        or range_end - range_start > MAX_RANGE
    ):
        raise HTTPException(
            status_code=422,
            detail={"reason": "invalid_history_range"},
        )
    try:
        return await run_in_threadpool(
            read_device_history,
            request.app.state.database_engine,
            device_id,
            range_start,
            range_end,
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"reason": "unknown_device"},
        ) from None
    except SQLAlchemyError:
        logger.warning("device_history_database_failed")
        raise HTTPException(
            status_code=503,
            detail={"reason": "history_unavailable"},
        ) from None
