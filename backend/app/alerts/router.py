"""Read-only HTTP API for persisted temperature alert episodes."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.alerts.schemas import AlertEpisodeList
from app.alerts.service import list_alert_episodes

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


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
