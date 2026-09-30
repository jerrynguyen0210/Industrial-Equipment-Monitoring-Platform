"""Persist telemetry-batch.v1 fields with authoritative event uniqueness.

Revision ID: 0002_telemetry
Revises: 0001_registry
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_telemetry"
down_revision = "0001_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telemetry",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("boot_id", sa.String(128), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_uptime_ms", sa.BigInteger(), nullable=False),
        sa.Column("gateway_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "backend_received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("quality", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telemetry")),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            name=op.f("fk_telemetry_device_id_devices"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "device_id", "boot_id", "sequence_number", name="uq_telemetry_identity"
        ),
        sa.CheckConstraint(
            "schema_version = 1", name=op.f("ck_telemetry_schema_version_v1")
        ),
        sa.CheckConstraint(
            "length(boot_id) > 0", name=op.f("ck_telemetry_boot_id_nonempty")
        ),
        sa.CheckConstraint(
            "sequence_number >= 0",
            name=op.f("ck_telemetry_sequence_number_nonnegative"),
        ),
        sa.CheckConstraint(
            "device_uptime_ms >= 0",
            name=op.f("ck_telemetry_device_uptime_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "metric = 'temperature'", name=op.f("ck_telemetry_metric_v1")
        ),
        sa.CheckConstraint("unit = 'celsius'", name=op.f("ck_telemetry_unit_v1")),
        sa.CheckConstraint(
            "value > '-Infinity'::numeric AND value < 'Infinity'::numeric",
            name=op.f("ck_telemetry_value_finite"),
        ),
        sa.CheckConstraint(
            "(jsonb_typeof(quality) = 'object' "
            "AND quality->>'reading' = 'valid' "
            "AND quality->>'clock' IN "
            "('synchronised', 'unsynchronised', 'estimated', 'unknown')) IS TRUE",
            name=op.f("ck_telemetry_quality_v1"),
        ),
    )
    op.create_index(
        "ix_telemetry_device_measured_at", "telemetry", ["device_id", "measured_at"]
    )
    op.create_index(
        "ix_telemetry_device_backend_received_at",
        "telemetry",
        ["device_id", "backend_received_at"],
    )


def downgrade() -> None:
    # Registry rows survive; telemetry rows cannot be recovered by upgrading again.
    op.drop_index("ix_telemetry_device_backend_received_at", table_name="telemetry")
    op.drop_index("ix_telemetry_device_measured_at", table_name="telemetry")
    op.drop_table("telemetry")
