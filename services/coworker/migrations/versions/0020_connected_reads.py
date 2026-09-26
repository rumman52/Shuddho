"""personal-agent connected read grants and cursor snapshots

Revision: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_connector_read_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("operation", sa.String(length=60), nullable=False),
        sa.Column("contract_version", sa.String(length=20), nullable=False),
        sa.Column("audience", sa.String(length=80), nullable=False),
        sa.Column("required_scopes", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("destination", sa.String(length=60), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id", "idempotency_key",
            name="uq_cw_connector_read_grants_owner_idempotency",
        ),
    )
    op.create_index("ix_cw_connector_read_grants_owner_id", "cw_connector_read_grants", ["owner_id"])
    op.create_index("ix_cw_connector_read_grants_connection_id", "cw_connector_read_grants", ["connection_id"])
    op.create_index("cw_connector_read_grants_owner_state", "cw_connector_read_grants", ["owner_id", "state"])
    op.create_index("cw_connector_read_grants_connection_state", "cw_connector_read_grants", ["connection_id", "state"])

    op.create_table(
        "cw_connector_cursors",
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("cursor", sa.String(length=1024), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["grant_id"], ["cw_connector_read_grants.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("grant_id"),
    )
    op.create_index("ix_cw_connector_cursors_owner_id", "cw_connector_cursors", ["owner_id"])
    op.create_index("ix_cw_connector_cursors_connection_id", "cw_connector_cursors", ["connection_id"])
    op.create_index("cw_connector_cursors_owner_updated", "cw_connector_cursors", ["owner_id", "updated_at"])
    op.create_index("cw_connector_cursors_connection", "cw_connector_cursors", ["connection_id"])

    op.create_table(
        "cw_connector_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("provider_resource_id", sa.String(length=512), nullable=False),
        sa.Column("provider_version", sa.String(length=128), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["grant_id"], ["cw_connector_read_grants.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grant_id", "provider_resource_id",
            name="uq_cw_connector_snapshots_grant_resource",
        ),
    )
    op.create_index("ix_cw_connector_snapshots_owner_id", "cw_connector_snapshots", ["owner_id"])
    op.create_index("ix_cw_connector_snapshots_grant_id", "cw_connector_snapshots", ["grant_id"])
    op.create_index("ix_cw_connector_snapshots_connection_id", "cw_connector_snapshots", ["connection_id"])
    op.create_index("cw_connector_snapshots_owner_updated", "cw_connector_snapshots", ["owner_id", "updated_at"])
    op.create_index("cw_connector_snapshots_grant_state", "cw_connector_snapshots", ["grant_id", "state"])

    op.add_column(
        "cw_agent_runs",
        sa.Column("connector_read_grant_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade():
    op.drop_column("cw_agent_runs", "connector_read_grant_ids")
    op.drop_index("cw_connector_snapshots_grant_state", table_name="cw_connector_snapshots")
    op.drop_index("cw_connector_snapshots_owner_updated", table_name="cw_connector_snapshots")
    op.drop_index("ix_cw_connector_snapshots_connection_id", table_name="cw_connector_snapshots")
    op.drop_index("ix_cw_connector_snapshots_grant_id", table_name="cw_connector_snapshots")
    op.drop_index("ix_cw_connector_snapshots_owner_id", table_name="cw_connector_snapshots")
    op.drop_table("cw_connector_snapshots")
    op.drop_index("cw_connector_cursors_connection", table_name="cw_connector_cursors")
    op.drop_index("cw_connector_cursors_owner_updated", table_name="cw_connector_cursors")
    op.drop_index("ix_cw_connector_cursors_connection_id", table_name="cw_connector_cursors")
    op.drop_index("ix_cw_connector_cursors_owner_id", table_name="cw_connector_cursors")
    op.drop_table("cw_connector_cursors")
    op.drop_index("cw_connector_read_grants_connection_state", table_name="cw_connector_read_grants")
    op.drop_index("cw_connector_read_grants_owner_state", table_name="cw_connector_read_grants")
    op.drop_index("ix_cw_connector_read_grants_connection_id", table_name="cw_connector_read_grants")
    op.drop_index("ix_cw_connector_read_grants_owner_id", table_name="cw_connector_read_grants")
    op.drop_table("cw_connector_read_grants")
