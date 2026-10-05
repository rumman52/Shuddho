"""TX-11 immutable shopping cart verification evidence.

Revision ID: 0051
Revises: 0050
"""
from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_shopping_cart_verifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_cart_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("merchant_cart_id", sa.String(length=255), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("mismatches", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sequence >= 1",
            name="ck_cw_shopping_cart_verifications_sequence",
        ),
        sa.CheckConstraint(
            "length(source_cart_sha256) = 64",
            name="ck_cw_shopping_cart_verifications_source_cart_sha256",
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name="ck_cw_shopping_cart_verifications_snapshot_sha256",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_shopping_cart_verifications_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            "sequence",
            name="uq_cw_shopping_cart_verifications_sequence",
        ),
    )
    op.create_index(
        "ix_cw_shopping_cart_verifications_owner_id",
        "cw_shopping_cart_verifications",
        ["owner_id"],
    )
    op.create_index(
        "cw_shopping_cart_verifications_owner_transaction",
        "cw_shopping_cart_verifications",
        ["owner_id", "transaction_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_shopping_cart_verifications_owner_transaction",
        table_name="cw_shopping_cart_verifications",
    )
    op.drop_index(
        "ix_cw_shopping_cart_verifications_owner_id",
        table_name="cw_shopping_cart_verifications",
    )
    op.drop_table("cw_shopping_cart_verifications")
