"""Core Agent Phase 3 durable execution checkpoints.

Revision ID: 0054
Revises: 0053
"""
from alembic import op
import sqlalchemy as sa

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_agent_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=36), nullable=True),
        sa.Column("invocation_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_key", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "checkpoint_key",
            name="uq_cw_agent_checkpoints_run_key",
        ),
    )
    op.create_index(
        "ix_cw_agent_checkpoints_run_id",
        "cw_agent_checkpoints",
        ["run_id"],
    )
    op.create_index(
        "ix_cw_agent_checkpoints_owner_id",
        "cw_agent_checkpoints",
        ["owner_id"],
    )
    op.create_index(
        "cw_agent_checkpoints_owner_run",
        "cw_agent_checkpoints",
        ["owner_id", "run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_agent_checkpoints_owner_run",
        table_name="cw_agent_checkpoints",
    )
    op.drop_index(
        "ix_cw_agent_checkpoints_owner_id",
        table_name="cw_agent_checkpoints",
    )
    op.drop_index(
        "ix_cw_agent_checkpoints_run_id",
        table_name="cw_agent_checkpoints",
    )
    op.drop_table("cw_agent_checkpoints")
