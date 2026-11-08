"""Persist project, artifact and steering context on conversation Agent runs.
Revision ID: 0065
Revises: 0064
"""
from alembic import op
import sqlalchemy as sa

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_agent_runs",
        sa.Column("input_artifacts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "cw_agent_runs",
        sa.Column("project_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "cw_agent_runs",
        sa.Column("steering_revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "cw_agent_runs",
        sa.Column("steering_instructions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade():
    op.drop_column("cw_agent_runs", "steering_instructions")
    op.drop_column("cw_agent_runs", "steering_revision")
    op.drop_column("cw_agent_runs", "project_context")
    op.drop_column("cw_agent_runs", "input_artifacts")
