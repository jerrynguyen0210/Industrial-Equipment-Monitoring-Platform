"""Database types that preserve absolute timestamp semantics."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Dialect, TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Use TIMESTAMPTZ, reject ambiguous inputs, and return UTC-aware instants."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Absolute timestamps must include a timezone")
        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(UTC)
