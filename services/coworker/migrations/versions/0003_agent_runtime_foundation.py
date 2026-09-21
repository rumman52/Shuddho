"""agent runtime foundation

Revision: 0003
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("output_language", sa.String(length=35), nullable=False),
        sa.Column("input_versions", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key"),
    )
    op.create_index("cw_agent_runs_owner_created", "cw_agent_runs", ["owner_id", "created_at"], unique=False)
    op.create_index("cw_agent_runs_state_deadline", "cw_agent_runs", ["state", "deadline_at"], unique=False)

    op.create_table(
        "cw_agent_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=True),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal"),
    )
    op.create_index(op.f("ix_cw_agent_steps_owner_id"), "cw_agent_steps", ["owner_id"], unique=False)
    op.create_index(op.f("ix_cw_agent_steps_run_id"), "cw_agent_steps", ["run_id"], unique=False)

    op.create_table(
        "cw_tool_invocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("tool_version", sa.String(length=20), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("consequential", sa.Boolean(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.ForeignKeyConstraint(["step_id"], ["cw_agent_steps.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id"),
    )
    op.create_index(op.f("ix_cw_tool_invocations_owner_id"), "cw_tool_invocations", ["owner_id"], unique=False)
    op.create_index(op.f("ix_cw_tool_invocations_run_id"), "cw_tool_invocations", ["run_id"], unique=False)

    op.create_table(
        "cw_tool_receipts",
        sa.Column("invocation_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invocation_id"], ["cw_tool_invocations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.PrimaryKeyConstraint("invocation_id"),
    )
    op.create_index(op.f("ix_cw_tool_receipts_owner_id"), "cw_tool_receipts", ["owner_id"], unique=False)
    op.create_index(op.f("ix_cw_tool_receipts_run_id"), "cw_tool_receipts", ["run_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_cw_tool_receipts_run_id"), table_name="cw_tool_receipts")
    op.drop_index(op.f("ix_cw_tool_receipts_owner_id"), table_name="cw_tool_receipts")
    op.drop_table("cw_tool_receipts")
    op.drop_index(op.f("ix_cw_tool_invocations_run_id"), table_name="cw_tool_invocations")
    op.drop_index(op.f("ix_cw_tool_invocations_owner_id"), table_name="cw_tool_invocations")
    op.drop_table("cw_tool_invocations")
    op.drop_index(op.f("ix_cw_agent_steps_run_id"), table_name="cw_agent_steps")
    op.drop_index(op.f("ix_cw_agent_steps_owner_id"), table_name="cw_agent_steps")
    op.drop_table("cw_agent_steps")
    op.drop_index("cw_agent_runs_state_deadline", table_name="cw_agent_runs")
    op.drop_index("cw_agent_runs_owner_created", table_name="cw_agent_runs")
    op.drop_table("cw_agent_runs")
