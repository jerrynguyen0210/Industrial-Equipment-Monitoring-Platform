"""Local platform health and authenticated telemetry ingestion API."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from app.config import database_conninfo
from app.database import create_database_engine
from app.device_api import router as device_router
from app.gateway_auth import load_gateway_credentials
from app.telemetry_api import router as telemetry_router
from app.telemetry_openapi import build_telemetry_openapi

logger = logging.getLogger("uvicorn.error")


class Health(BaseModel):
    status: Literal["ok"]


class Readiness(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "unavailable"]


def check_database() -> None:
    """Authenticate and execute a query, with bounded connection/query times."""
    with psycopg.connect(
        database_conninfo(),
        connect_timeout=3,
        options="-c statement_timeout=2000",
        autocommit=True,
    ) as connection:
        connection.execute("SELECT 1").fetchone()


def create_app(
    database_probe: Callable[[], None] = check_database,
    *,
    engine_factory: Callable[[], Engine] = create_database_engine,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database_conninfo()
        application.state.gateway_credentials = load_gateway_credentials()
        engine = engine_factory()
        application.state.database_engine = engine
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="Industrial Equipment Monitoring Platform",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/health", response_model=Health)
    @application.get("/api/health/live", response_model=Health)
    def live() -> Health:
        """Report API liveness without checking dependencies."""
        return Health(status="ok")

    @application.get(
        "/ready",
        response_model=Readiness,
        responses={503: {"model": Readiness, "description": "Database unavailable"}},
    )
    @application.get(
        "/api/health/ready",
        response_model=Readiness,
        responses={503: {"model": Readiness, "description": "Database unavailable"}},
    )
    def ready() -> Readiness | JSONResponse:
        """Check database authentication and query execution on every request."""
        try:
            database_probe()
        except psycopg.Error:
            # Connection errors may include credentials or infrastructure details.
            logger.warning("database_readiness_failed")
            return JSONResponse(
                status_code=503,
                content=Readiness(
                    status="unavailable", database="unavailable"
                ).model_dump(),
            )
        return Readiness(status="ready", database="ok")

    application.include_router(telemetry_router)
    application.include_router(device_router)

    def openapi() -> dict:
        if application.openapi_schema is None:
            schema = get_openapi(
                title=application.title,
                version=application.version,
                routes=application.routes,
            )
            contract = build_telemetry_openapi()
            schema["paths"].update(contract["paths"])
            for section, definitions in contract["components"].items():
                schema["components"].setdefault(section, {}).update(definitions)
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = openapi
    return application


app = create_app()
