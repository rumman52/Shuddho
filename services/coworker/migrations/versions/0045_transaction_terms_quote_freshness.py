"""TX-03 exact transaction terms, quote, and freshness evidence.

Revision ID: 0045
Revises: 0044

Adds immutable terms snapshots bound to transaction revisions. This migration
adds no provider mutation path and no new transaction operation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_transactions",
        sa.Column("current_terms_revision", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("cw_transactions") as batch_op:
        batch_op.create_check_constraint(
            "ck_cw_transactions_current_terms_revision",
            "current_terms_revision IS NULL OR current_terms_revision >= 1",
        )

    op.create_table(
        "cw_transaction_terms",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("price", sa.JSON(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("terms_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider_quote_id", sa.String(length=255), nullable=True),
        sa.Column("quoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_cw_transaction_terms_revision"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_cw_transaction_terms_currency",
        ),
        sa.CheckConstraint("total_minor >= 0", name="ck_cw_transaction_terms_total_minor"),
        sa.CheckConstraint("length(terms_sha256) = 64", name="ck_cw_transaction_terms_sha256"),
        sa.CheckConstraint(
            "quote_expires_at > quoted_at",
            name="ck_cw_transaction_terms_quote_window",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_transaction_terms_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id", "revision"),
    )
    op.create_index(
        "ix_cw_transaction_terms_owner_id",
        "cw_transaction_terms",
        ["owner_id"],
    )
    op.create_index(
        "cw_transaction_terms_owner_transaction_revision",
        "cw_transaction_terms",
        ["owner_id", "transaction_id", "revision"],
    )
    op.create_index(
        "cw_transaction_terms_quote_expiry",
        "cw_transaction_terms",
        ["quote_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_transaction_terms_quote_expiry",
        table_name="cw_transaction_terms",
    )
    op.drop_index(
        "cw_transaction_terms_owner_transaction_revision",
        table_name="cw_transaction_terms",
    )
    op.drop_index(
        "ix_cw_transaction_terms_owner_id",
        table_name="cw_transaction_terms",
    )
    op.drop_table("cw_transaction_terms")
    with op.batch_alter_table("cw_transactions") as batch_op:
        batch_op.drop_constraint(
            "ck_cw_transactions_current_terms_revision",
            type_="check",
        )
        batch_op.drop_column("current_terms_revision")
