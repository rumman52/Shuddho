"""TX-02 generic transaction domain foundation.

Revision ID: 0044
Revises: 0043

Adds owner-scoped business transaction state separate from ExternalAction.
This migration adds no provider authority and no new enabled operation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


TRANSACTION_STATES = (
    "draft",
    "terms_ready",
    "awaiting_review",
    "awaiting_approval",
    "approved",
    "executing",
    "confirmed",
    "cancelled",
    "expired",
    "failed",
    "outcome_unknown",
)


def _state_check(column: str) -> str:
    values = ",".join(f"'{value}'" for value in TRANSACTION_STATES)
    return f"{column} IN ({values})"


def upgrade() -> None:
    op.create_table(
        "cw_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("transaction_kind", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_account_ref", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("counterparty", sa.String(length=300), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_state_check("state"), name="ck_cw_transactions_state"),
        sa.CheckConstraint("revision >= 1", name="ck_cw_transactions_revision"),
        sa.CheckConstraint(
            "currency IS NULL OR (length(currency) = 3 AND currency = upper(currency))",
            name="ck_cw_transactions_currency",
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_id", name="uq_cw_transactions_id_owner"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_cw_transactions_owner_idempotency",
        ),
    )
    op.create_index("ix_cw_transactions_owner_id", "cw_transactions", ["owner_id"])
    op.create_index("ix_cw_transactions_workspace_id", "cw_transactions", ["workspace_id"])
    op.create_index("ix_cw_transactions_connection_id", "cw_transactions", ["connection_id"])
    op.create_index("cw_transactions_owner_updated", "cw_transactions", ["owner_id", "updated_at"])
    op.create_index("cw_transactions_workspace_state", "cw_transactions", ["workspace_id", "state"])
    op.create_index("cw_transactions_provider_state", "cw_transactions", ["provider", "state"])

    op.create_table(
        "cw_transaction_revisions",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_cw_transaction_revisions_revision"),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_transaction_revisions_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id", "revision"),
    )
    op.create_index("ix_cw_transaction_revisions_owner_id", "cw_transaction_revisions", ["owner_id"])
    op.create_index(
        "cw_transaction_revisions_owner_transaction",
        "cw_transaction_revisions",
        ["owner_id", "transaction_id"],
    )

    op.create_table(
        "cw_transaction_events",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_cw_transaction_events_sequence"),
        sa.CheckConstraint("revision >= 1", name="ck_cw_transaction_events_revision"),
        sa.CheckConstraint(_state_check("state"), name="ck_cw_transaction_events_state"),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_transaction_events_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id", "sequence"),
    )
    op.create_index("ix_cw_transaction_events_owner_id", "cw_transaction_events", ["owner_id"])
    op.create_index(
        "cw_transaction_events_owner_transaction_sequence",
        "cw_transaction_events",
        ["owner_id", "transaction_id", "sequence"],
    )

    op.create_table(
        "cw_transaction_execution_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("transaction_revision", sa.Integer(), nullable=False),
        sa.Column("external_action_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transaction_revision >= 1",
            name="ck_cw_transaction_execution_links_revision",
        ),
        sa.ForeignKeyConstraint(["external_action_id"], ["cw_external_actions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_transaction_execution_links_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_action_id"),
    )
    op.create_index(
        "ix_cw_transaction_execution_links_transaction_id",
        "cw_transaction_execution_links",
        ["transaction_id"],
    )
    op.create_index(
        "ix_cw_transaction_execution_links_owner_id",
        "cw_transaction_execution_links",
        ["owner_id"],
    )
    op.create_index(
        "ix_cw_transaction_execution_links_external_action_id",
        "cw_transaction_execution_links",
        ["external_action_id"],
    )
    op.create_index(
        "cw_transaction_execution_links_owner_transaction",
        "cw_transaction_execution_links",
        ["owner_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_transaction_execution_links_owner_transaction",
        table_name="cw_transaction_execution_links",
    )
    op.drop_index(
        "ix_cw_transaction_execution_links_external_action_id",
        table_name="cw_transaction_execution_links",
    )
    op.drop_index(
        "ix_cw_transaction_execution_links_owner_id",
        table_name="cw_transaction_execution_links",
    )
    op.drop_index(
        "ix_cw_transaction_execution_links_transaction_id",
        table_name="cw_transaction_execution_links",
    )
    op.drop_table("cw_transaction_execution_links")

    op.drop_index(
        "cw_transaction_events_owner_transaction_sequence",
        table_name="cw_transaction_events",
    )
    op.drop_index(
        "ix_cw_transaction_events_owner_id",
        table_name="cw_transaction_events",
    )
    op.drop_table("cw_transaction_events")

    op.drop_index(
        "cw_transaction_revisions_owner_transaction",
        table_name="cw_transaction_revisions",
    )
    op.drop_index(
        "ix_cw_transaction_revisions_owner_id",
        table_name="cw_transaction_revisions",
    )
    op.drop_table("cw_transaction_revisions")

    op.drop_index("cw_transactions_provider_state", table_name="cw_transactions")
    op.drop_index("cw_transactions_workspace_state", table_name="cw_transactions")
    op.drop_index("cw_transactions_owner_updated", table_name="cw_transactions")
    op.drop_index("ix_cw_transactions_connection_id", table_name="cw_transactions")
    op.drop_index("ix_cw_transactions_workspace_id", table_name="cw_transactions")
    op.drop_index("ix_cw_transactions_owner_id", table_name="cw_transactions")
    op.drop_table("cw_transactions")
