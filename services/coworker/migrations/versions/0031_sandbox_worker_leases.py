"""PA-08 durable sandbox worker leases and results.

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_sandbox_executions",
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "cw_sandbox_executions",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("cw_sandbox_executions", sa.Column("claimed_by", sa.String(length=64)))
    op.add_column(
        "cw_sandbox_executions",
        sa.Column("lease_until", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "cw_sandbox_executions",
        sa.Column("started_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "cw_sandbox_executions_state_lease",
        "cw_sandbox_executions",
        ["state", "lease_until"],
    )


def downgrade():
    op.drop_index(
        "cw_sandbox_executions_state_lease",
        table_name="cw_sandbox_executions",
    )
    op.drop_column("cw_sandbox_executions", "started_at")
    op.drop_column("cw_sandbox_executions", "lease_until")
    op.drop_column("cw_sandbox_executions", "claimed_by")
    op.drop_column("cw_sandbox_executions", "attempts")
    op.drop_column("cw_sandbox_executions", "result")
