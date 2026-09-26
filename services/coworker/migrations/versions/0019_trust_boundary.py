"""personal-agent deterministic connector trust boundary

Revision: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_execution_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=20), nullable=False),
        sa.Column("action_kind", sa.String(length=30), nullable=False),
        sa.Column("action_version", sa.String(length=20), nullable=False),
        sa.Column("audience", sa.String(length=80), nullable=False),
        sa.Column("required_scopes", sa.JSON(), nullable=False),
        sa.Column("destinations_sha256", sa.String(length=64), nullable=False),
        sa.Column("preview_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], ["cw_external_actions.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id", "purpose", "preview_hash",
            name="uq_cw_execution_grants_action_purpose_preview",
        ),
    )
    op.create_index("ix_cw_execution_grants_owner_id", "cw_execution_grants", ["owner_id"])
    op.create_index("ix_cw_execution_grants_action_id", "cw_execution_grants", ["action_id"])
    op.create_index("ix_cw_execution_grants_connection_id", "cw_execution_grants", ["connection_id"])
    op.create_index("cw_execution_grants_owner_state", "cw_execution_grants", ["owner_id", "state"])
    op.create_index("cw_execution_grants_action_created", "cw_execution_grants", ["action_id", "created_at"])
    op.create_index("cw_execution_grants_connection_state", "cw_execution_grants", ["connection_id", "state"])


def downgrade():
    op.drop_index("cw_execution_grants_connection_state", table_name="cw_execution_grants")
    op.drop_index("cw_execution_grants_action_created", table_name="cw_execution_grants")
    op.drop_index("cw_execution_grants_owner_state", table_name="cw_execution_grants")
    op.drop_index("ix_cw_execution_grants_connection_id", table_name="cw_execution_grants")
    op.drop_index("ix_cw_execution_grants_action_id", table_name="cw_execution_grants")
    op.drop_index("ix_cw_execution_grants_owner_id", table_name="cw_execution_grants")
    op.drop_table("cw_execution_grants")
