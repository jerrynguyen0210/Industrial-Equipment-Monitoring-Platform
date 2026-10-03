"""Persisted equipment registry and telemetry event identities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import UTCDateTime
from app.telemetry.time import event_time


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (CheckConstraint("length(site_id) > 0", name="site_id_nonempty"),)

    site_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    gateways: Mapped[list[Gateway]] = relationship(
        back_populates="site", passive_deletes="all"
    )


class Gateway(Base):
    __tablename__ = "gateways"
    __table_args__ = (
        CheckConstraint("length(gateway_id) > 0", name="gateway_id_nonempty"),
    )

    gateway_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(
        ForeignKey("sites.site_id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    site: Mapped[Site] = relationship(back_populates="gateways")
    devices: Mapped[list[Device]] = relationship(
        back_populates="gateway", passive_deletes="all"
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("length(device_id) > 0", name="device_id_nonempty"),
    )

    # Global identity, not a gateway-scoped composite key. PostgreSQL is the
    # authority even when two writers attempt to register the same ID concurrently.
    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    gateway_id: Mapped[str] = mapped_column(
        ForeignKey("gateways.gateway_id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    gateway: Mapped[Gateway] = relationship(back_populates="devices")
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mqtt_managed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "boot_id", "sequence_number", name="uq_telemetry_identity"
        ),
        CheckConstraint("schema_version = 1", name="schema_version_v1"),
        CheckConstraint("length(boot_id) > 0", name="boot_id_nonempty"),
        CheckConstraint("sequence_number >= 0", name="sequence_number_nonnegative"),
        CheckConstraint("device_uptime_ms >= 0", name="device_uptime_ms_nonnegative"),
        CheckConstraint("metric = 'temperature'", name="metric_v1"),
        CheckConstraint("unit = 'celsius'", name="unit_v1"),
        CheckConstraint(
            "value > '-Infinity'::numeric AND value < 'Infinity'::numeric",
            name="value_finite",
        ),
        CheckConstraint(
            "(jsonb_typeof(quality) = 'object' "
            "AND quality->>'reading' = 'valid' "
            "AND quality->>'clock' IN "
            "('synchronised', 'unsynchronised', 'estimated', 'unknown')) IS TRUE",
            name="quality_v1",
        ),
        Index("ix_telemetry_device_measured_at", "device_id", "measured_at"),
        Index(
            "ix_telemetry_device_backend_received_at",
            "device_id",
            "backend_received_at",
        ),
    )

    # This surrogate key is internal; retry identity is the unique domain triple.
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    schema_version: Mapped[int] = mapped_column(SmallInteger)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.device_id", ondelete="RESTRICT")
    )
    # Contract fixtures include "boot-a", so this must not be restricted to UUIDs.
    boot_id: Mapped[str] = mapped_column(String(128))
    sequence_number: Mapped[int] = mapped_column(BigInteger)
    measured_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    device_uptime_ms: Mapped[int] = mapped_column(BigInteger)
    gateway_received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    backend_received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.clock_timestamp()
    )
    metric: Mapped[str] = mapped_column(String(32))
    # No fixed scale: preserve decimal content for later immutable comparison.
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(String(32))
    quality: Mapped[dict[str, str]] = mapped_column(JSONB)


# Both the per-device latest-reading lookup and bounded history use this order.
Index(
    "ix_telemetry_device_event_at",
    Telemetry.device_id,
    event_time(Telemetry).desc(),
    Telemetry.id.desc(),
)


class AlertEpisode(Base):
    """One temperature alert from opening through recovery."""

    __tablename__ = "alert_episodes"
    __table_args__ = (
        UniqueConstraint(
            "opening_telemetry_id", name="uq_alert_episodes_opening_telemetry_id"
        ),
        UniqueConstraint(
            "resolving_telemetry_id", name="uq_alert_episodes_resolving_telemetry_id"
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at",
            name="resolution_after_opening",
        ),
        Index(
            "uq_alert_episodes_active_device",
            "device_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.device_id", ondelete="RESTRICT"), index=True
    )
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    opening_telemetry_id: Mapped[int] = mapped_column(
        ForeignKey("telemetry.id", ondelete="RESTRICT")
    )
    resolving_telemetry_id: Mapped[int | None] = mapped_column(
        ForeignKey("telemetry.id", ondelete="RESTRICT")
    )


class AlertState(Base):
    """Last evaluated event and debounce counters for one device."""

    __tablename__ = "alert_states"
    __table_args__ = (
        UniqueConstraint("active_episode_id", name="uq_alert_states_active_episode_id"),
        CheckConstraint("high_streak BETWEEN 0 AND 2", name="high_streak_range"),
        CheckConstraint(
            "recovery_streak BETWEEN 0 AND 2", name="recovery_streak_range"
        ),
    )

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.device_id", ondelete="RESTRICT"), primary_key=True
    )
    last_event_at: Mapped[datetime] = mapped_column(UTCDateTime())
    high_streak: Mapped[int] = mapped_column(SmallInteger, default=0)
    recovery_streak: Mapped[int] = mapped_column(SmallInteger, default=0)
    active_episode_id: Mapped[int | None] = mapped_column(
        ForeignKey("alert_episodes.id", ondelete="RESTRICT")
    )
