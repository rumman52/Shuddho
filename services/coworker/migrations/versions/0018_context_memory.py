"""personal-agent context retrieval and reviewable memory proposals

Revision: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_memory_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=60), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False, server_default="auto"),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="proposed"),
        sa.Column("accepted_fact_id", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["accepted_fact_id"], ["cw_memory_facts.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cw_memory_proposals_owner_id", "cw_memory_proposals", ["owner_id"])
    op.create_index("ix_cw_memory_proposals_workspace_id", "cw_memory_proposals", ["workspace_id"])
    op.create_index("ix_cw_memory_proposals_run_id", "cw_memory_proposals", ["run_id"])
    op.create_index("cw_memory_proposals_owner_state", "cw_memory_proposals", ["owner_id", "state"])
    op.create_index("cw_memory_proposals_run_created", "cw_memory_proposals", ["run_id", "created_at"])


def downgrade():
    op.drop_index("cw_memory_proposals_run_created", table_name="cw_memory_proposals")
    op.drop_index("cw_memory_proposals_owner_state", table_name="cw_memory_proposals")
    op.drop_index("ix_cw_memory_proposals_run_id", table_name="cw_memory_proposals")
    op.drop_index("ix_cw_memory_proposals_workspace_id", table_name="cw_memory_proposals")
    op.drop_index("ix_cw_memory_proposals_owner_id", table_name="cw_memory_proposals")
    op.drop_table("cw_memory_proposals")
