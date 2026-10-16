"""Persist one exact human review decision per inert code proposal.

Revision ID: 0057
Revises: 0056
"""
from alembic import op
import sqlalchemy as sa

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_agent_code_reviews",
        sa.Column(
            "proposal_id", sa.String(36),
            sa.ForeignKey("cw_agent_code_proposals.id"), primary_key=True,
        ),
        sa.Column(
            "run_id", sa.String(36),
            sa.ForeignKey("cw_agent_runs.id"), nullable=False,
        ),
        sa.Column(
            "owner_id", sa.String(64),
            sa.ForeignKey("cw_accounts.id"), nullable=False,
        ),
        sa.Column("review_sha256", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject')",
            name="ck_cw_agent_code_review_decision",
        ),
    )
    op.create_index("ix_cw_agent_code_reviews_run_id", "cw_agent_code_reviews", ["run_id"])
    op.create_index("ix_cw_agent_code_reviews_owner_id", "cw_agent_code_reviews", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_cw_agent_code_reviews_owner_id", table_name="cw_agent_code_reviews")
    op.drop_index("ix_cw_agent_code_reviews_run_id", table_name="cw_agent_code_reviews")
    op.drop_table("cw_agent_code_reviews")
