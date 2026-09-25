"""The minimum persisted site -> gateway -> device registry."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, MetaData, String, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
