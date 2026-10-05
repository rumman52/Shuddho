"""TX-09 immutable travel quote verification evidence.

Revision ID: 0049
Revises: 0048
"""
from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_travel_quote_verifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_quote_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_quote_id", sa.String(length=255), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("mismatches", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_cw_travel_quote_verifications_sequence"),
        sa.CheckConstraint(
            "length(source_quote_sha256) = 64",
            name="ck_cw_travel_quote_verifications_source_quote_sha256",
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name="ck_cw_travel_quote_verifications_snapshot_sha256",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_travel_quote_verifications_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            "sequence",
            name="uq_cw_travel_quote_verifications_sequence",
        ),
    )
    op.create_index(
        "ix_cw_travel_quote_verifications_owner_id",
        "cw_travel_quote_verifications",
        ["owner_id"],
    )
    op.create_index(
        "cw_travel_quote_verifications_owner_transaction",
        "cw_travel_quote_verifications",
        ["owner_id", "transaction_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_travel_quote_verifications_owner_transaction",
        table_name="cw_travel_quote_verifications",
    )
    op.drop_index(
        "ix_cw_travel_quote_verifications_owner_id",
        table_name="cw_travel_quote_verifications",
    )
    op.drop_table("cw_travel_quote_verifications")
