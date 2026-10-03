"""Track broker accounts created through device management.

Revision ID: 0006_mqtt_management
Revises: 0005_device_presence
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_mqtt_management"
down_revision = "0005_device_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "mqtt_managed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "mqtt_managed")
