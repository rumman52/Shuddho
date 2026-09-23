"""non-executable agent action proposals

Revision: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_action_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.String(length=300), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("promotion_connection_id", sa.String(length=36), nullable=True),
        sa.Column("promoted_action_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["cw_agent_runs.id"]),
        sa.ForeignKeyConstraint(["promotion_connection_id"], ["cw_connections.id"]),
        sa.ForeignKeyConstraint(["promoted_action_id"], ["cw_external_actions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "cw_action_proposals_run_created",
        "cw_action_proposals",
        ["agent_run_id", "created_at"],
    )
    op.create_index(
        "cw_action_proposals_owner_state",
        "cw_action_proposals",
        ["owner_id", "state"],
    )


def downgrade():
    op.drop_index("cw_action_proposals_owner_state", table_name="cw_action_proposals")
    op.drop_index("cw_action_proposals_run_created", table_name="cw_action_proposals")
    op.drop_table("cw_action_proposals")
