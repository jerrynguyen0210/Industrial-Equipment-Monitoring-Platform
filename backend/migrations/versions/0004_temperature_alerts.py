"""Store one evaluation cursor and temperature alert episodes per device.

Revision ID: 0004_temperature_alerts
Revises: 0003_event_time_index
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_temperature_alerts"
down_revision = "0003_event_time_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_episodes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_telemetry_id", sa.BigInteger(), nullable=False),
        sa.Column("resolving_telemetry_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_episodes")),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            name=op.f("fk_alert_episodes_device_id_devices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opening_telemetry_id"],
            ["telemetry.id"],
            name=op.f("fk_alert_episodes_opening_telemetry_id_telemetry"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolving_telemetry_id"],
            ["telemetry.id"],
            name=op.f("fk_alert_episodes_resolving_telemetry_id_telemetry"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "opening_telemetry_id", name="uq_alert_episodes_opening_telemetry_id"
        ),
        sa.UniqueConstraint(
            "resolving_telemetry_id", name="uq_alert_episodes_resolving_telemetry_id"
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at",
            name=op.f("ck_alert_episodes_resolution_after_opening"),
        ),
    )
    op.create_index(
        op.f("ix_alert_episodes_device_id"), "alert_episodes", ["device_id"]
    )
    op.create_index(
        "uq_alert_episodes_active_device",
        "alert_episodes",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "alert_states",
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("high_streak", sa.SmallInteger(), nullable=False),
        sa.Column("recovery_streak", sa.SmallInteger(), nullable=False),
        sa.Column("active_episode_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("device_id", name=op.f("pk_alert_states")),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.device_id"],
            name=op.f("fk_alert_states_device_id_devices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["active_episode_id"],
            ["alert_episodes.id"],
            name=op.f("fk_alert_states_active_episode_id_alert_episodes"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "active_episode_id", name="uq_alert_states_active_episode_id"
        ),
        sa.CheckConstraint(
            "high_streak BETWEEN 0 AND 2",
            name=op.f("ck_alert_states_high_streak_range"),
        ),
        sa.CheckConstraint(
            "recovery_streak BETWEEN 0 AND 2",
            name=op.f("ck_alert_states_recovery_streak_range"),
        ),
    )


def downgrade() -> None:
    op.drop_table("alert_states")
    op.drop_index("uq_alert_episodes_active_device", table_name="alert_episodes")
    op.drop_index(op.f("ix_alert_episodes_device_id"), table_name="alert_episodes")
    op.drop_table("alert_episodes")
