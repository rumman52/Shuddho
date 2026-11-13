"""Add an inert, durable reviewed task brief snapshot to Agent runs."""
from alembic import op
import sqlalchemy as sa

revision = "0069_conversation_task_briefs"
down_revision = "0068_fly_repository_coding"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("cw_agent_runs", sa.Column(
        "reviewed_brief", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

def downgrade():
    op.drop_column("cw_agent_runs", "reviewed_brief")
