"""Add inert owner-bound CW-10 generated-code proposal snapshots.

Revision ID: 0056
Revises: 0055
"""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_agent_code_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("cw_agent_runs.id"), nullable=False),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("review_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "idempotency_key",
            name="uq_cw_agent_code_proposal_run_key",
        ),
    )
    op.create_index(
        "ix_cw_agent_code_proposals_run_id",
        "cw_agent_code_proposals", ["run_id"],
    )
    op.create_index(
        "ix_cw_agent_code_proposals_owner_id",
        "cw_agent_code_proposals", ["owner_id"],
    )
    op.create_index(
        "cw_agent_code_proposals_owner_run",
        "cw_agent_code_proposals", ["owner_id", "run_id"],
    )


def downgrade() -> None:
    op.drop_index("cw_agent_code_proposals_owner_run", table_name="cw_agent_code_proposals")
    op.drop_index("ix_cw_agent_code_proposals_owner_id", table_name="cw_agent_code_proposals")
    op.drop_index("ix_cw_agent_code_proposals_run_id", table_name="cw_agent_code_proposals")
    op.drop_table("cw_agent_code_proposals")
