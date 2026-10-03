"""Compatibility import for existing deployment scripts; use app.db.session."""

from app.db.session import create_database_engine as create_database_engine
