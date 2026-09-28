"""PA-08 sandbox control plane.

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_sandbox_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("cw_workspaces.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("runtime", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="prepared"),
        sa.Column("execution_policy", sa.JSON(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cleanup_state", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_sandbox_sessions_owner_idempotency"),
    )
    op.create_index("ix_cw_sandbox_sessions_owner_id", "cw_sandbox_sessions", ["owner_id"])
    op.create_index("ix_cw_sandbox_sessions_workspace_id", "cw_sandbox_sessions", ["workspace_id"])
    op.create_index("cw_sandbox_sessions_owner_created", "cw_sandbox_sessions", ["owner_id", "created_at"])
    op.create_index("cw_sandbox_sessions_state_expiry", "cw_sandbox_sessions", ["state", "expires_at"])

    op.create_table(
        "cw_sandbox_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("cw_sandbox_sessions.id"), nullable=False),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_bytes", sa.Integer(), nullable=False),
        sa.Column("request_spec", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="prepared"),
        sa.Column("error_code", sa.String(length=60)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "sequence", name="uq_cw_sandbox_executions_session_sequence"),
    )
    op.create_index("ix_cw_sandbox_executions_session_id", "cw_sandbox_executions", ["session_id"])
    op.create_index("ix_cw_sandbox_executions_owner_id", "cw_sandbox_executions", ["owner_id"])
    op.create_index("cw_sandbox_executions_owner_session", "cw_sandbox_executions", ["owner_id", "session_id"])


def downgrade():
    op.drop_table("cw_sandbox_executions")
    op.drop_table("cw_sandbox_sessions")
