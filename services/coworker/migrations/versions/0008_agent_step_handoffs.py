"""typed agent step handoffs

Revision: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_tasks", sa.Column("agent_step_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_cw_tasks_agent_step_id"), "cw_tasks", ["agent_step_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_cw_tasks_agent_step_id"), table_name="cw_tasks")
    op.drop_column("cw_tasks", "agent_step_id")
