"""Bind code-reviewed sandbox executions to their immutable proposal.

Revision ID: 0058
Revises: 0057
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_sandbox_executions",
        sa.Column(
            "agent_code_proposal_id",
            sa.String(36),
            sa.ForeignKey("cw_agent_code_proposals.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cw_sandbox_executions_agent_code_proposal_id",
        "cw_sandbox_executions",
        ["agent_code_proposal_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cw_sandbox_executions_agent_code_proposal_id",
        table_name="cw_sandbox_executions",
    )
    op.drop_column("cw_sandbox_executions", "agent_code_proposal_id")
