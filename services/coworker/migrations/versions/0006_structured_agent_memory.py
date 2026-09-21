"""structured agent memory

Revision: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_tasks", sa.Column("agent_run_id", sa.String(length=36), nullable=True))
    op.add_column("cw_agent_runs", sa.Column("memory_namespaces", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.create_index(op.f("ix_cw_tasks_agent_run_id"), "cw_tasks", ["agent_run_id"], unique=False)
    op.create_table(
        "cw_memory_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=60), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=35), nullable=False),
        sa.Column("provenance_type", sa.String(length=30), nullable=False),
        sa.Column("provenance_ref", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "workspace_id", "namespace", "key"),
    )
    op.create_index(op.f("ix_cw_memory_facts_owner_id"), "cw_memory_facts", ["owner_id"], unique=False)
    op.create_index(op.f("ix_cw_memory_facts_workspace_id"), "cw_memory_facts", ["workspace_id"], unique=False)
    op.create_index("cw_memory_owner_updated", "cw_memory_facts", ["owner_id", "updated_at"], unique=False)
    op.create_index("cw_memory_workspace_namespace", "cw_memory_facts", ["workspace_id", "namespace"], unique=False)


def downgrade():
    op.drop_index("cw_memory_workspace_namespace", table_name="cw_memory_facts")
    op.drop_index("cw_memory_owner_updated", table_name="cw_memory_facts")
    op.drop_index(op.f("ix_cw_memory_facts_workspace_id"), table_name="cw_memory_facts")
    op.drop_index(op.f("ix_cw_memory_facts_owner_id"), table_name="cw_memory_facts")
    op.drop_table("cw_memory_facts")
    op.drop_index(op.f("ix_cw_tasks_agent_run_id"), table_name="cw_tasks")
    op.drop_column("cw_agent_runs", "memory_namespaces")
    op.drop_column("cw_tasks", "agent_run_id")
