"""Persist provider-reported token direction for planner and child attempts."""
from alembic import op
import sqlalchemy as sa

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cw_agent_runs", sa.Column("planner_input_tokens", sa.Integer(), nullable=True))
    op.add_column("cw_agent_runs", sa.Column("planner_output_tokens", sa.Integer(), nullable=True))
    op.add_column("cw_model_attempts", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("cw_model_attempts", sa.Column("output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cw_model_attempts", "output_tokens")
    op.drop_column("cw_model_attempts", "input_tokens")
    op.drop_column("cw_agent_runs", "planner_output_tokens")
    op.drop_column("cw_agent_runs", "planner_input_tokens")
