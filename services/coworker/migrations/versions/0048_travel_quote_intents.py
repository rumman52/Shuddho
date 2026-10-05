"""TX-08 durable review-only travel quote intents.

Revision ID: 0048
Revises: 0047
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_travel_quote_intents",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("quote", sa.JSON(), nullable=False),
        sa.Column("quote_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(quote_sha256) = 64",
            name="ck_cw_travel_quote_intents_quote_sha256",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_travel_quote_intents_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.create_index(
        "ix_cw_travel_quote_intents_owner_id",
        "cw_travel_quote_intents",
        ["owner_id"],
    )
    op.create_index(
        "cw_travel_quote_intents_owner_transaction",
        "cw_travel_quote_intents",
        ["owner_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_travel_quote_intents_owner_transaction",
        table_name="cw_travel_quote_intents",
    )
    op.drop_index(
        "ix_cw_travel_quote_intents_owner_id",
        table_name="cw_travel_quote_intents",
    )
    op.drop_table("cw_travel_quote_intents")
