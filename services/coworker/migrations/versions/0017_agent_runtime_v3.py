"""personal-agent runtime v3 decision ledger and frozen routing

Revision: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_agent_runs",
        sa.Column("runtime_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "cw_agent_runs",
        sa.Column("planner_actual_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cw_agent_runs",
        sa.Column("planner_cost_microusd", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_cw_agent_runs_runtime_version", "cw_agent_runs", ["runtime_version"])

    op.create_table(
        "cw_agent_decisions",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("planner_call", sa.Integer(), nullable=False),
        sa.Column("decision_type", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("tool_schema_sha256", sa.String(length=64), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_microusd", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("run_id", "sequence"),
        sa.UniqueConstraint("run_id", "planner_call", name="uq_cw_agent_decisions_planner_call"),
    )
    op.create_index("ix_cw_agent_decisions_owner_id", "cw_agent_decisions", ["owner_id"])
    op.create_index("cw_agent_decisions_owner_run", "cw_agent_decisions", ["owner_id", "run_id"])


def downgrade():
    op.drop_index("cw_agent_decisions_owner_run", table_name="cw_agent_decisions")
    op.drop_index("ix_cw_agent_decisions_owner_id", table_name="cw_agent_decisions")
    op.drop_table("cw_agent_decisions")
    op.drop_index("ix_cw_agent_runs_runtime_version", table_name="cw_agent_runs")
    op.drop_column("cw_agent_runs", "planner_cost_microusd")
    op.drop_column("cw_agent_runs", "planner_actual_tokens")
    op.drop_column("cw_agent_runs", "runtime_version")
