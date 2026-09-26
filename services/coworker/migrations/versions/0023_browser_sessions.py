"""PA-07 browser broker control plane.

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_browser_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("cw_workspaces.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("start_url", sa.Text(), nullable=False),
        sa.Column("start_origin", sa.String(length=512), nullable=False),
        sa.Column("allowed_origins", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="prepared"),
        sa.Column("takeover_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("worker_session_ref", sa.String(length=128)),
        sa.Column("last_url", sa.Text()),
        sa.Column("last_title", sa.String(length=300)),
        sa.Column("error_code", sa.String(length=60)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_browser_sessions_owner_idempotency"),
    )
    op.create_index("ix_cw_browser_sessions_owner_id", "cw_browser_sessions", ["owner_id"])
    op.create_index("ix_cw_browser_sessions_workspace_id", "cw_browser_sessions", ["workspace_id"])
    op.create_index("cw_browser_sessions_owner_created", "cw_browser_sessions", ["owner_id", "created_at"])
    op.create_index("cw_browser_sessions_state_expiry", "cw_browser_sessions", ["state", "expires_at"])

    op.create_table(
        "cw_browser_commands",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("cw_browser_sessions.id"), nullable=False),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("target_url", sa.Text()),
        sa.Column("target_origin", sa.String(length=512)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="prepared"),
        sa.Column("error_code", sa.String(length=60)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "sequence", name="uq_cw_browser_commands_session_sequence"),
    )
    op.create_index("ix_cw_browser_commands_session_id", "cw_browser_commands", ["session_id"])
    op.create_index("ix_cw_browser_commands_owner_id", "cw_browser_commands", ["owner_id"])
    op.create_index("cw_browser_commands_owner_session", "cw_browser_commands", ["owner_id", "session_id"])


def downgrade():
    op.drop_table("cw_browser_commands")
    op.drop_table("cw_browser_sessions")
