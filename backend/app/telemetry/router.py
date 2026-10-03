"""HTTP endpoints for authenticated ingestion and bounded history."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.core.gateway_auth import resolve_gateway
from app.telemetry.schemas import DeviceHistory, TelemetryBatchResponse
from app.telemetry.service import (
    DeviceNotFoundError,
    GatewayForbiddenError,
    InvalidHistoryRangeError,
    ingest_batch,
    read_device_history,
)
from app.telemetry.validation import read_telemetry_batch

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


@router.post(
    "/api/v1/telemetry/batches",
    response_model=TelemetryBatchResponse,
    response_model_exclude_unset=True,
)
async def ingest_telemetry(
    request: Request, gateway_id: Annotated[str, Depends(resolve_gateway)]
) -> TelemetryBatchResponse:
    batch = await read_telemetry_batch(request)
    batch_id = str(uuid4())
    try:
        committed_response = await run_in_threadpool(
            ingest_batch, request.app.state.database_engine, gateway_id, batch, batch_id
        )
    except GatewayForbiddenError:
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "gateway_not_authorized",
                "message": "Gateway is not enabled for ingestion.",
                "batch_id": batch_id,
            },
        ) from None
    except SQLAlchemyError:
        # Driver exceptions can contain secrets and payloads, including on commit.
        logger.warning("telemetry_database_failed", extra={"batch_id": batch_id})
        raise HTTPException(
            status_code=503,
            detail={
                "reason": "ingestion_unavailable",
                "message": "Batch unconfirmed; retry with unchanged event identities.",
                "batch_id": batch_id,
            },
        ) from None
    return committed_response


@router.get("/api/v1/devices/{device_id}/telemetry", response_model=DeviceHistory)
@router.get(
    "/api/v1/devices/{device_id}/telemetry/history",
    response_model=DeviceHistory,
    include_in_schema=False,
)
async def get_device_history(
    request: Request,
    device_id: str,
    range_start: Annotated[datetime, Query(alias="from")],
    range_end: Annotated[datetime, Query(alias="to")],
) -> DeviceHistory:
    try:
        return await run_in_threadpool(
            read_device_history,
            request.app.state.database_engine,
            device_id,
            range_start,
            range_end,
        )
    except InvalidHistoryRangeError:
        raise HTTPException(
            status_code=422,
            detail={"reason": "invalid_history_range"},
        ) from None
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
