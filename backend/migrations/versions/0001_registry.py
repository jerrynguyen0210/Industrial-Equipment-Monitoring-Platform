"""Create the minimum site, gateway, and device registry.

Revision ID: 0001_registry
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_registry"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("site_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(
            "length(site_id) > 0", name=op.f("ck_sites_site_id_nonempty")
        ),
        sa.PrimaryKeyConstraint("site_id", name=op.f("pk_sites")),
    )
    op.create_table(
        "gateways",
        sa.Column("gateway_id", sa.String(128), nullable=False),
        sa.Column("site_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(
            "length(gateway_id) > 0", name=op.f("ck_gateways_gateway_id_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.site_id"],
            name=op.f("fk_gateways_site_id_sites"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("gateway_id", name=op.f("pk_gateways")),
    )
    op.create_index(op.f("ix_gateways_site_id"), "gateways", ["site_id"])
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("gateway_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(
            "length(device_id) > 0", name=op.f("ck_devices_device_id_nonempty")
        ),
        sa.ForeignKeyConstraint(
            ["gateway_id"],
            ["gateways.gateway_id"],
            name=op.f("fk_devices_gateway_id_gateways"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("device_id", name=op.f("pk_devices")),
    )
    op.create_index(op.f("ix_devices_gateway_id"), "devices", ["gateway_id"])


def downgrade() -> None:
    # Destructive by definition: only exercise rollback on disposable test data.
    op.drop_index(op.f("ix_devices_gateway_id"), table_name="devices")
    op.drop_table("devices")
    op.drop_index(op.f("ix_gateways_site_id"), table_name="gateways")
    op.drop_table("gateways")
    op.drop_table("sites")
