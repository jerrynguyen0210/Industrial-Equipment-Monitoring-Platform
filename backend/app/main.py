"""Compose feature routers and manage application dependencies."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine

from app.alerts.router import router as alert_router
from app.core.config import database_conninfo
from app.core.gateway_auth import load_gateway_credentials
from app.core.health import check_database, create_health_router
from app.db.session import create_database_engine
from app.devices.router import router as device_router
from app.integrations.mqtt import BrokerAdmin
from app.telemetry.openapi import install_telemetry_openapi
from app.telemetry.router import router as telemetry_router


def create_app(
    database_probe: Callable[[], None] = check_database,
    *,
    engine_factory: Callable[[], Engine] = create_database_engine,
    broker_factory: Callable[[], BrokerAdmin] = BrokerAdmin.from_environment,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database_conninfo()
        application.state.gateway_credentials = load_gateway_credentials()
        engine = engine_factory()
        application.state.database_engine = engine
        application.state.broker_admin = broker_factory()
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
    application.include_router(create_health_router(database_probe))
    application.include_router(telemetry_router)
    application.include_router(device_router)
    application.include_router(alert_router)
    install_telemetry_openapi(application)
    return application


app = create_app()
