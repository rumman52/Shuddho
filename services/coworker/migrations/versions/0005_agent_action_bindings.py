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
    op.add_column("cw_external_actions", sa.Column("agent_run_id", sa.String(length=36), nullable=True))
    op.add_column("cw_external_actions", sa.Column("agent_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("cw_external_actions", "agent_ready", server_default=None)
    op.create_index(op.f("ix_cw_external_actions_agent_run_id"), "cw_external_actions", ["agent_run_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_cw_external_actions_agent_run_id"), table_name="cw_external_actions")
    op.drop_column("cw_external_actions", "agent_ready")
    op.drop_column("cw_external_actions", "agent_run_id")
    op.drop_column("cw_agent_runs", "action_ids")
