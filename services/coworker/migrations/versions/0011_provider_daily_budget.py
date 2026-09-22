"""global provider daily token budget

Revision: 0011
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_provider_daily_usage",
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("allocated_tokens", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade():
    op.drop_table("cw_provider_daily_usage")
