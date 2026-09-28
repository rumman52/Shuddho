"""PA-09 durable negotiation case ledger.

Revision ID: 0033
Revises: 0032
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_negotiation_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("counterparty_name", sa.String(length=300), nullable=False),
        sa.Column("counterparty_address", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_cw_negotiation_cases_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_cw_negotiation_cases_owner_id",
        "cw_negotiation_cases",
        ["owner_id"],
    )
    op.create_index(
        "ix_cw_negotiation_cases_workspace_id",
        "cw_negotiation_cases",
        ["workspace_id"],
    )
    op.create_index(
        "ix_cw_negotiation_cases_connection_id",
        "cw_negotiation_cases",
        ["connection_id"],
    )
    op.create_index(
        "cw_negotiation_cases_owner_updated",
        "cw_negotiation_cases",
        ["owner_id", "updated_at"],
    )
    op.create_index(
        "cw_negotiation_cases_connection_state",
        "cw_negotiation_cases",
        ["connection_id", "state"],
    )

    op.create_table(
        "cw_negotiation_case_revisions",
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cw_negotiation_cases.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("case_id", "revision"),
    )
    op.create_index(
        "ix_cw_negotiation_case_revisions_owner_id",
        "cw_negotiation_case_revisions",
        ["owner_id"],
    )
    op.create_index(
        "cw_negotiation_case_revisions_owner_case",
        "cw_negotiation_case_revisions",
        ["owner_id", "case_id"],
    )

    op.create_table(
        "cw_negotiation_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("external_action_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cw_negotiation_cases.id"]),
        sa.ForeignKeyConstraint(["external_action_id"], ["cw_external_actions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_cw_negotiation_offers_owner_idempotency",
        ),
        sa.UniqueConstraint(
            "case_id",
            "sequence",
            name="uq_cw_negotiation_offers_case_sequence",
        ),
        sa.UniqueConstraint("external_action_id"),
    )
    op.create_index(
        "ix_cw_negotiation_offers_case_id",
        "cw_negotiation_offers",
        ["case_id"],
    )
    op.create_index(
        "ix_cw_negotiation_offers_owner_id",
        "cw_negotiation_offers",
        ["owner_id"],
    )
    op.create_index(
        "ix_cw_negotiation_offers_external_action_id",
        "cw_negotiation_offers",
        ["external_action_id"],
    )
    op.create_index(
        "cw_negotiation_offers_owner_case_sequence",
        "cw_negotiation_offers",
        ["owner_id", "case_id", "sequence"],
    )


def downgrade():
    op.drop_index(
        "cw_negotiation_offers_owner_case_sequence",
        table_name="cw_negotiation_offers",
    )
    op.drop_index(
        "ix_cw_negotiation_offers_external_action_id",
        table_name="cw_negotiation_offers",
    )
    op.drop_index(
        "ix_cw_negotiation_offers_owner_id",
        table_name="cw_negotiation_offers",
    )
    op.drop_index(
        "ix_cw_negotiation_offers_case_id",
        table_name="cw_negotiation_offers",
    )
    op.drop_table("cw_negotiation_offers")
    op.drop_index(
        "cw_negotiation_case_revisions_owner_case",
        table_name="cw_negotiation_case_revisions",
    )
    op.drop_index(
        "ix_cw_negotiation_case_revisions_owner_id",
        table_name="cw_negotiation_case_revisions",
    )
    op.drop_table("cw_negotiation_case_revisions")
    op.drop_index(
        "cw_negotiation_cases_connection_state",
        table_name="cw_negotiation_cases",
    )
    op.drop_index(
        "cw_negotiation_cases_owner_updated",
        table_name="cw_negotiation_cases",
    )
    op.drop_index(
        "ix_cw_negotiation_cases_connection_id",
        table_name="cw_negotiation_cases",
    )
    op.drop_index(
        "ix_cw_negotiation_cases_workspace_id",
        table_name="cw_negotiation_cases",
    )
    op.drop_index(
        "ix_cw_negotiation_cases_owner_id",
        table_name="cw_negotiation_cases",
    )
    op.drop_table("cw_negotiation_cases")
