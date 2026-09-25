"""Explicit SQLAlchemy engines using the same configuration as readiness."""

from psycopg.conninfo import conninfo_to_dict
from sqlalchemy import Engine, create_engine

from app.config import database_conninfo


def create_database_engine() -> Engine:
    """Create a lazy engine; the caller owns its lifetime and transactions."""
    settings = conninfo_to_dict(database_conninfo())
    settings["connect_timeout"] = "3"
    settings["options"] = (
        settings.get("options", "") + " -c statement_timeout=5000 -c lock_timeout=5000"
    ).strip()
    # Pass libpq settings directly: retain SSL/query options and encoded passwords
    # without putting credentials into Alembic's interpolated config or engine URL.
    return create_engine(
        "postgresql+psycopg://",
        connect_args=settings,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=5,
        hide_parameters=True,
    )
