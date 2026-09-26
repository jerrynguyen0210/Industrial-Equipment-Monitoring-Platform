"""Read-only API for current device readings."""

import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import Engine, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import lateral
from starlette.concurrency import run_in_threadpool

from app.device_schemas import DeviceStatus, DeviceStatusList, LatestReading
from app.models import Device, Telemetry

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def list_device_status(engine: Engine) -> DeviceStatusList:
    """Return every registered device and its most recently received reading."""
    latest = lateral(
        select(
            Telemetry.value,
            Telemetry.unit,
            Telemetry.measured_at,
            Telemetry.quality["clock"].as_string().label("clock_quality"),
        )
        .where(Telemetry.device_id == Device.device_id)
        .order_by(Telemetry.backend_received_at.desc(), Telemetry.id.desc())
        .limit(1)
    ).alias("latest_reading")
    statement = (
        select(
            Device.device_id,
            Device.name,
            latest.c.value,
            latest.c.unit,
            latest.c.measured_at,
            latest.c.clock_quality,
        )
        .select_from(Device)
        .outerjoin(latest, true())
        .order_by(Device.name, Device.device_id)
    )

    with Session(engine) as session:
        rows = session.execute(statement).all()

    return DeviceStatusList(
        devices=[
            DeviceStatus(
                device_id=row.device_id,
                name=row.name,
                latest_reading=(
                    LatestReading(
                        value=row.value,
                        unit=row.unit,
                        measured_at=row.measured_at,
                        clock_quality=row.clock_quality,
                    )
                    if row.value is not None
                    else None
                ),
            )
            for row in rows
        ]
    )


@router.get("/api/v1/devices", response_model=DeviceStatusList)
async def get_devices(request: Request) -> DeviceStatusList:
    """List devices with latest telemetry, returning safe dependency errors."""
    try:
        return await run_in_threadpool(
            list_device_status, request.app.state.database_engine
        )
    except SQLAlchemyError:
        logger.warning("device_status_database_failed")
        raise HTTPException(
            status_code=503,
            detail={"reason": "device_status_unavailable"},
        ) from None
