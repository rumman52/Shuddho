"""bounded intelligent planner

Revision: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_agent_runs", sa.Column("planner_calls", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cw_agent_runs", sa.Column("planner_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cw_agent_runs", sa.Column("planner_mode", sa.String(length=30), nullable=False, server_default="deterministic"))


def downgrade():
    op.drop_column("cw_agent_runs", "planner_mode")
    op.drop_column("cw_agent_runs", "planner_tokens")
    op.drop_column("cw_agent_runs", "planner_calls")
