"""agent approval action bindings

Revision: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_agent_runs", sa.Column("action_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.alter_column("cw_agent_runs", "action_ids", server_default=None)


def downgrade():
    op.drop_column("cw_agent_runs", "action_ids")
