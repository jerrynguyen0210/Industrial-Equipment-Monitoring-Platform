"""HTTP adapter for the authenticated, independently classified telemetry batch."""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.gateway_auth import resolve_gateway
from app.ingestion import GatewayForbiddenError, ingest_batch
from app.telemetry_schemas import TelemetryBatchResponse
from app.telemetry_validation import read_telemetry_batch

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
        return await run_in_threadpool(
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
