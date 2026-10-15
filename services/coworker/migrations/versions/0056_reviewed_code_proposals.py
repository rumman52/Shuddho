"""Add owner-scoped immutable code reviews; default-off and old-worker compatible."""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_reviewed_code_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("cw_agent_runs.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("review_sha256", sa.String(64), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("cw_sandbox_sessions.id")),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("cw_sandbox_executions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_code_review_owner_key"),
    )
    op.create_index("ix_cw_reviewed_code_proposals_owner_id", "cw_reviewed_code_proposals", ["owner_id"])
    op.create_index("ix_cw_reviewed_code_proposals_agent_run_id", "cw_reviewed_code_proposals", ["agent_run_id"])
    op.create_index("cw_code_review_owner_state_expiry", "cw_reviewed_code_proposals", ["owner_id", "state", "expires_at"])


def downgrade():
    op.drop_table("cw_reviewed_code_proposals")
