"""Explicit database settings with errors that never include secret values."""

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def database_conninfo() -> str:
    """Prefer a PostgreSQL URL; retain the local Compose PG* configuration."""
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("DATABASE_URL must be a PostgreSQL URL")
        try:
            settings = conninfo_to_dict(database_url)
        except psycopg.ProgrammingError:
            raise RuntimeError("DATABASE_URL is not a valid PostgreSQL URL") from None
        required = ("host", "dbname", "user", "password")
        missing = [name for name in required if not settings.get(name)]
        if missing:
            raise RuntimeError(f"DATABASE_URL is missing: {', '.join(missing)}")
        settings.setdefault("port", "5432")
        port_name = "DATABASE_URL port"
    else:
        variables = {
            "host": "PGHOST",
            "port": "PGPORT",
            "dbname": "PGDATABASE",
            "user": "PGUSER",
            "password": "PGPASSWORD",
        }
        missing = [name for name in variables.values() if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Missing database configuration: {', '.join(missing)}")
        settings = {key: os.environ[name] for key, name in variables.items()}
        port_name = "PGPORT"
    port = settings["port"]
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError(f"{port_name} must be a number between 1 and 65535")
    return make_conninfo(**settings)
