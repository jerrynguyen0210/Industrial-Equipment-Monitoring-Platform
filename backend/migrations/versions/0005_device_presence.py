"""Store device heartbeat credentials and last contact time.

Revision ID: 0005_device_presence
Revises: 0004_temperature_alerts
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_device_presence"
down_revision = "0004_temperature_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("password_hash", sa.String(200), nullable=True))
    op.add_column(
        "devices", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("devices", "last_seen_at")
    op.drop_column("devices", "password_hash")
