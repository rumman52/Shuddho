"""shared provider capacity leases

Revision: 0010
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_provider_leases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lease_key", sa.String(length=160), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_key"),
    )
    op.create_index(
        "ix_cw_provider_leases_owner_id",
        "cw_provider_leases",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_cw_provider_leases_expires_at",
        "cw_provider_leases",
        ["expires_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_cw_provider_leases_expires_at", table_name="cw_provider_leases")
    op.drop_index("ix_cw_provider_leases_owner_id", table_name="cw_provider_leases")
    op.drop_table("cw_provider_leases")
