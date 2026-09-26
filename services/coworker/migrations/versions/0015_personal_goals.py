"""persistent personal goals and immutable goal revision links

Revision: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "cw_personal_goals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("success_criteria", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("constraints", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("milestones", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("budget", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("authorized_resources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_personal_goals_owner_idempotency"),
    )
    op.create_index("ix_cw_personal_goals_owner_id", "cw_personal_goals", ["owner_id"])
    op.create_index("ix_cw_personal_goals_workspace_id", "cw_personal_goals", ["workspace_id"])
    op.create_index("cw_personal_goals_owner_created", "cw_personal_goals", ["owner_id", "created_at"])
    op.create_index("cw_personal_goals_workspace_state", "cw_personal_goals", ["workspace_id", "state"])
    op.create_table(
        "cw_personal_goal_revisions",
        sa.Column("goal_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["cw_personal_goals.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("goal_id", "revision"),
    )
    op.create_index("ix_cw_personal_goal_revisions_owner_id", "cw_personal_goal_revisions", ["owner_id"])
    op.create_index("cw_personal_goal_revisions_owner_goal", "cw_personal_goal_revisions", ["owner_id", "goal_id"])
    op.add_column("cw_agent_runs", sa.Column("goal_id", sa.String(length=36), nullable=True))
    op.add_column("cw_agent_runs", sa.Column("goal_revision", sa.Integer(), nullable=True))
    op.create_index("ix_cw_agent_runs_goal_id", "cw_agent_runs", ["goal_id"])

def downgrade():
    op.drop_index("ix_cw_agent_runs_goal_id", table_name="cw_agent_runs")
    op.drop_column("cw_agent_runs", "goal_revision")
    op.drop_column("cw_agent_runs", "goal_id")
    op.drop_index("cw_personal_goal_revisions_owner_goal", table_name="cw_personal_goal_revisions")
    op.drop_index("ix_cw_personal_goal_revisions_owner_id", table_name="cw_personal_goal_revisions")
    op.drop_table("cw_personal_goal_revisions")
    op.drop_index("cw_personal_goals_workspace_state", table_name="cw_personal_goals")
    op.drop_index("cw_personal_goals_owner_created", table_name="cw_personal_goals")
    op.drop_index("ix_cw_personal_goals_workspace_id", table_name="cw_personal_goals")
    op.drop_index("ix_cw_personal_goals_owner_id", table_name="cw_personal_goals")
    op.drop_table("cw_personal_goals")
