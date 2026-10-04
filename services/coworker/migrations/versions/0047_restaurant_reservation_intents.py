"""TX-06 immutable no-payment restaurant reservation intents.

Revision ID: 0047
Revises: 0046
"""
from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_restaurant_reservation_intents",
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("availability", sa.JSON(), nullable=False),
        sa.Column("availability_sha256", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name="ck_cw_restaurant_reservation_intents_request_sha256",
        ),
        sa.CheckConstraint(
            "length(availability_sha256) = 64",
            name="ck_cw_restaurant_reservation_intents_availability_sha256",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_restaurant_reservation_intents_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("transaction_id"),
    )
    op.create_index(
        "ix_cw_restaurant_reservation_intents_owner_id",
        "cw_restaurant_reservation_intents",
        ["owner_id"],
    )
    op.create_index(
        "cw_restaurant_reservation_intents_owner_transaction",
        "cw_restaurant_reservation_intents",
        ["owner_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_restaurant_reservation_intents_owner_transaction",
        table_name="cw_restaurant_reservation_intents",
    )
    op.drop_index(
        "ix_cw_restaurant_reservation_intents_owner_id",
        table_name="cw_restaurant_reservation_intents",
    )
    op.drop_table("cw_restaurant_reservation_intents")
