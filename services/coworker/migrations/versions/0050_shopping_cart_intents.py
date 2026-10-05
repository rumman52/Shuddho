"""TX-10 durable review-only shopping cart intents.

Revision ID: 0050
Revises: 0049
"""
from alembic import op
import sqlalchemy as sa

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_shopping_cart_intents",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("cart", sa.JSON(), nullable=False),
        sa.Column("cart_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(cart_sha256) = 64",
            name="ck_cw_shopping_cart_intents_cart_sha256",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_shopping_cart_intents_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.create_index(
        "ix_cw_shopping_cart_intents_owner_id",
        "cw_shopping_cart_intents",
        ["owner_id"],
    )
    op.create_index(
        "cw_shopping_cart_intents_owner_transaction",
        "cw_shopping_cart_intents",
        ["owner_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_shopping_cart_intents_owner_transaction",
        table_name="cw_shopping_cart_intents",
    )
    op.drop_index(
        "ix_cw_shopping_cart_intents_owner_id",
        table_name="cw_shopping_cart_intents",
    )
    op.drop_table("cw_shopping_cart_intents")
