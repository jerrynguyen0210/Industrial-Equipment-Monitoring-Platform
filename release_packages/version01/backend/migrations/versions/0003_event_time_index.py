"""Index the effective event time used by dashboard reads.

Revision ID: 0003_event_time_index
Revises: 0002_telemetry
"""

from alembic import op

revision = "0003_event_time_index"
down_revision = "0002_telemetry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_telemetry_device_event_at ON telemetry "
        "(device_id, (CASE WHEN measured_at IS NOT NULL "
        "AND quality->>'clock' = 'synchronised' "
        "THEN measured_at ELSE gateway_received_at END) DESC, id DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_device_event_at", table_name="telemetry")
