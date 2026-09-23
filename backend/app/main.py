"""Local platform health API; telemetry ingestion is a separate workstream."""

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("uvicorn.error")


class Health(BaseModel):
    status: Literal["ok", "ready", "unavailable"]
    database: Literal["ok", "unavailable"] | None = None


def check_database() -> None:
    """Authenticate and execute a query, with bounded connection/query times."""
    with psycopg.connect(
        connect_timeout=3,
        options="-c statement_timeout=2000",
        autocommit=True,
    ) as connection:
        connection.execute("SELECT 1").fetchone()


def create_app(database_probe: Callable[[], None] = check_database) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Missing database configuration: {', '.join(missing)}")
        port = os.environ["PGPORT"]
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise RuntimeError("PGPORT must be a number between 1 and 65535")
        yield

    application = FastAPI(
        title="Industrial Equipment Monitoring Platform",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/api/health/live", response_model_exclude_none=True)
    def live() -> Health:
        return Health(status="ok")

    @application.get("/api/health/ready", response_model=Health)
    def ready() -> Health | JSONResponse:
        try:
            database_probe()
        except psycopg.Error:
            # Connection errors may include credentials or infrastructure details.
            logger.warning("database_readiness_failed")
            return JSONResponse(
                status_code=503,
                content=Health(
                    status="unavailable", database="unavailable"
                ).model_dump(),
            )
        return Health(status="ready", database="ok")

    return application


app = create_app()
