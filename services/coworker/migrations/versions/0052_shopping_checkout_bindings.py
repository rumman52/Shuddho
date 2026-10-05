"""TX-12 immutable shopping checkout approval bindings.

Revision ID: 0052
Revises: 0051
"""
from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_shopping_checkout_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("verification_id", sa.String(length=36), nullable=False),
        sa.Column("transaction_revision", sa.Integer(), nullable=False),
        sa.Column("terms_revision", sa.Integer(), nullable=False),
        sa.Column("terms_sha256", sa.String(length=64), nullable=False),
        sa.Column("cart_sha256", sa.String(length=64), nullable=False),
        sa.Column("verification_snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("merchant_cart_id", sa.String(length=255), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("approval_scope_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transaction_revision >= 1 AND terms_revision >= 1",
            name="ck_cw_shopping_checkout_bindings_revisions",
        ),
        sa.CheckConstraint(
            "length(terms_sha256) = 64",
            name="ck_cw_shopping_checkout_bindings_terms_sha256",
        ),
        sa.CheckConstraint(
            "length(cart_sha256) = 64",
            name="ck_cw_shopping_checkout_bindings_cart_sha256",
        ),
        sa.CheckConstraint(
            "length(verification_snapshot_sha256) = 64",
            name="ck_cw_shopping_checkout_bindings_verification_snapshot_sha256",
        ),
        sa.CheckConstraint(
            "length(approval_scope_sha256) = 64",
            name="ck_cw_shopping_checkout_bindings_scope_sha256",
        ),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_cw_shopping_checkout_bindings_currency",
        ),
        sa.CheckConstraint(
            "total_minor >= 0",
            name="ck_cw_shopping_checkout_bindings_total_minor",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_shopping_checkout_bindings_transaction_owner",
        ),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["cw_shopping_cart_verifications.id"],
            name="fk_cw_shopping_checkout_bindings_verification",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            name="uq_cw_shopping_checkout_bindings_transaction",
        ),
    )
    op.create_index(
        "ix_cw_shopping_checkout_bindings_owner_id",
        "cw_shopping_checkout_bindings",
        ["owner_id"],
    )
    op.create_index(
        "cw_shopping_checkout_bindings_owner_transaction",
        "cw_shopping_checkout_bindings",
        ["owner_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_shopping_checkout_bindings_owner_transaction",
        table_name="cw_shopping_checkout_bindings",
    )
    op.drop_index(
        "ix_cw_shopping_checkout_bindings_owner_id",
        table_name="cw_shopping_checkout_bindings",
    )
    op.drop_table("cw_shopping_checkout_bindings")
