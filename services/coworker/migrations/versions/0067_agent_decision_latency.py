"""Persist measured Runtime v3 planner inference latency.
Revision ID: 0067
Revises: 0066
"""
from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_agent_decisions",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("cw_agent_decisions", "latency_ms")
