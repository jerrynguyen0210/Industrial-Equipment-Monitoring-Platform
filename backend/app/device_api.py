"""Device registration, presence, and current readings."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import Engine, select, true, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import lateral
from starlette.concurrency import run_in_threadpool

from app.device_credentials import hash_password, verify_password
from app.device_schemas import (
    DeviceStatus,
    DeviceStatusList,
    GatewayList,
    GatewayOption,
    LatestReading,
)
from app.models import Device, Gateway, Site, Telemetry
from app.mqtt_admin import BrokerAdmin, BrokerConflict, BrokerUnavailable
from app.telemetry_time import event_time

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
ONLINE_WINDOW = timedelta(seconds=90)


class DeviceRegistration(BaseModel):
    device_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    gateway_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class DeviceHeartbeat(BaseModel):
    password: str


def list_gateways(engine: Engine) -> GatewayList:
    with Session(engine) as session:
        rows = session.execute(
            select(Gateway.gateway_id, Gateway.name)
            .join(Gateway.site)
            .where(Gateway.enabled, Gateway.site.has(enabled=True))
            .order_by(Gateway.name, Gateway.gateway_id)
        ).all()
    return GatewayList(
        gateways=[GatewayOption.model_validate(row._mapping) for row in rows]
    )


def register_device(
    engine: Engine, broker: BrokerAdmin, registration: DeviceRegistration
) -> DeviceStatus:
    broker_created = False
    try:
        with Session(engine) as session, session.begin():
            gateway = session.execute(
                select(Gateway)
                .where(Gateway.gateway_id == registration.gateway_id)
                .with_for_update(read=True)
            ).scalar_one_or_none()
            if gateway is None or not gateway.enabled or not gateway.site.enabled:
                raise HTTPException(
                    status_code=404, detail={"reason": "gateway_not_found"}
                )
            device = Device(
                device_id=registration.device_id,
                gateway_id=registration.gateway_id,
                name=registration.name.strip(),
                password_hash=hash_password(registration.password),
                mqtt_managed=False,
            )
            if not device.name:
                raise HTTPException(status_code=422, detail={"reason": "name_required"})
            session.add(device)
            session.flush()
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
            device = session.execute(
                select(Device).where(Device.device_id == device_id).with_for_update()
            ).scalar_one_or_none()
            if device is None:
                raise HTTPException(
                    status_code=404, detail={"reason": "device_not_found"}
                )
            managed = device.mqtt_managed
            session.delete(device)
            session.flush()
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
        device = session.execute(
            select(Device).where(Device.device_id == device_id).with_for_update()
        ).scalar_one_or_none()
        if device is None or not verify_password(password, device.password_hash):
            raise HTTPException(
                status_code=401, detail={"reason": "invalid_device_credentials"}
            )
        device.mqtt_managed = broker.ensure_device(device_id, password)


def record_heartbeat(engine: Engine, device_id: str, password: str) -> None:
    with Session(engine) as session, session.begin():
        device = session.execute(
            select(Device).where(Device.device_id == device_id).with_for_update()
        ).scalar_one_or_none()
        if (
            device is None
            or not device.enabled
            or not device.gateway.enabled
            or not device.gateway.site.enabled
            or not verify_password(password, device.password_hash)
        ):
            raise HTTPException(
                status_code=401, detail={"reason": "invalid_device_credentials"}
            )
        session.execute(
            update(Device)
            .where(Device.device_id == device_id)
            .values(last_seen_at=datetime.now(UTC))
        )


def list_device_status(engine: Engine) -> DeviceStatusList:
    """Return every registered device and its newest reading by event time."""
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

    with Session(engine) as session:
        rows = session.execute(statement).all()

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


@router.get("/api/v1/gateways", response_model=GatewayList)
async def get_gateways(request: Request) -> GatewayList:
    try:
        return await run_in_threadpool(list_gateways, request.app.state.database_engine)
    except SQLAlchemyError:
        logger.warning("gateway_list_database_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "registry_unavailable"}
        ) from None


@router.post(
    "/api/v1/devices",
    response_model=DeviceStatus,
    status_code=status.HTTP_201_CREATED,
)
async def post_device(
    request: Request, registration: DeviceRegistration
) -> DeviceStatus:
    try:
        return await run_in_threadpool(
            register_device,
            request.app.state.database_engine,
            request.app.state.broker_admin,
            registration,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail={"reason": "device_id_exists"}
        ) from None
    except SQLAlchemyError:
        logger.warning("device_registration_database_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "registry_unavailable"}
        ) from None
    except BrokerConflict:
        raise HTTPException(
            status_code=409, detail={"reason": "mqtt_account_exists"}
        ) from None
    except BrokerUnavailable:
        logger.warning("device_registration_broker_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "mqtt_broker_unavailable"}
        ) from None


@router.post("/api/v1/devices/{device_id}/mqtt", status_code=204)
async def post_existing_device_mqtt(
    request: Request, device_id: str, credentials: DeviceHeartbeat
) -> None:
    try:
        await run_in_threadpool(
            configure_existing_mqtt,
            request.app.state.database_engine,
            request.app.state.broker_admin,
            device_id,
            credentials.password,
        )
    except SQLAlchemyError:
        logger.warning("existing_device_mqtt_database_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "registry_unavailable"}
        ) from None
    except BrokerConflict:
        raise HTTPException(
            status_code=409, detail={"reason": "mqtt_account_exists"}
        ) from None
    except BrokerUnavailable:
        logger.warning("existing_device_mqtt_broker_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "mqtt_broker_unavailable"}
        ) from None


@router.post("/api/v1/devices/{device_id}/heartbeat", status_code=204)
async def post_heartbeat(
    request: Request, device_id: str, heartbeat: DeviceHeartbeat
) -> None:
    try:
        await run_in_threadpool(
            record_heartbeat,
            request.app.state.database_engine,
            device_id,
            heartbeat.password,
        )
    except SQLAlchemyError:
        logger.warning("device_heartbeat_database_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "registry_unavailable"}
        ) from None


@router.delete("/api/v1/devices/{device_id}", status_code=204)
async def delete_device(request: Request, device_id: str) -> None:
    try:
        await run_in_threadpool(
            remove_device,
            request.app.state.database_engine,
            request.app.state.broker_admin,
            device_id,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail={"reason": "device_has_history"}
        ) from None
    except SQLAlchemyError:
        logger.warning("device_delete_database_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "registry_unavailable"}
        ) from None
    except BrokerConflict:
        raise HTTPException(
            status_code=409, detail={"reason": "mqtt_account_conflict"}
        ) from None
    except BrokerUnavailable:
        logger.warning("device_delete_broker_failed")
        raise HTTPException(
            status_code=503, detail={"reason": "mqtt_broker_unavailable"}
        ) from None


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
