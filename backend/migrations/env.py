"""Run versioned migrations with the backend's explicit database configuration."""

from alembic import context
from app.db.models import Base
from app.db.session import create_database_engine
from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError

config = context.config


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    # PostgreSQL renders JSONB expression indexes with extra casts/parentheses.
    # Alembic treats the same index as a remove/add pair; its DDL is checked by
    # a PostgreSQL integration test instead of unreliable text comparison.
    if type_ == "index" and name == "ix_telemetry_device_event_at":
        return False
    return True


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    # Rendering SQL neither needs nor exposes a configured database credential.
    context.configure(
        dialect_name="postgresql",
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    # Integration tests can supply their own isolated connection/transaction.
    migrate(config.attributes["connection"])
else:
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            migrate(connection)
    except SQLAlchemyError:
        raise SystemExit(
            "Database migration failed; check database access and schema revision"
        ) from None
    finally:
        engine.dispose()
