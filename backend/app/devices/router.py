"""HTTP endpoints for device registration, presence, and current readings."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.devices.schemas import (
    DeviceHeartbeat,
    DeviceRegistration,
    DeviceStatus,
    DeviceStatusList,
    GatewayList,
)
from app.devices.service import (
    DeviceNotFoundError,
    GatewayNotFoundError,
    InvalidDeviceCredentialsError,
    NameRequiredError,
    configure_existing_mqtt,
    list_device_status,
    list_gateways,
    record_heartbeat,
    register_device,
    remove_device,
)
from app.integrations.mqtt import BrokerConflict, BrokerUnavailable

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


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
    except GatewayNotFoundError:
        raise HTTPException(
            status_code=404, detail={"reason": "gateway_not_found"}
        ) from None
    except NameRequiredError:
        raise HTTPException(
            status_code=422, detail={"reason": "name_required"}
        ) from None
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
    except InvalidDeviceCredentialsError:
        raise HTTPException(
            status_code=401, detail={"reason": "invalid_device_credentials"}
        ) from None
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
    except InvalidDeviceCredentialsError:
        raise HTTPException(
            status_code=401, detail={"reason": "invalid_device_credentials"}
        ) from None
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
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=404, detail={"reason": "device_not_found"}
        ) from None
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
