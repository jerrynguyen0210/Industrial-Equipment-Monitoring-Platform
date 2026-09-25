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
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.types import UTCDateTime


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
