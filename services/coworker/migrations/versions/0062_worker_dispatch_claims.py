"""Persist worker dispatch claims so drains cannot certify in-flight work.

Revision ID: 0062
Revises: 0061
"""
from alembic import op
import sqlalchemy as sa

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_worker_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "worker_id",
            sa.String(36),
            sa.ForeignKey("cw_worker_instances.id"),
            nullable=False,
        ),
        sa.Column("task_queue", sa.String(160), nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "claim_type IN ('task_dispatch','agent_dispatch','action_dispatch')",
            name="ck_cw_worker_claims_claim_type",
        ),
        sa.CheckConstraint(
            "state IN ('active','completed')",
            name="ck_cw_worker_claims_state",
        ),
    )
    op.create_index(
        "cw_worker_claims_worker_state_claimed",
        "cw_worker_claims",
        ["worker_id", "state", "claimed_at"],
    )
    op.create_index(
        "cw_worker_claims_queue_state",
        "cw_worker_claims",
        ["task_queue", "state"],
    )
    op.create_index(
        "uq_cw_worker_claims_active_resource",
        "cw_worker_claims",
        ["worker_id", "claim_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_cw_worker_claims_active_resource",
        table_name="cw_worker_claims",
    )
    op.drop_index(
        "cw_worker_claims_queue_state",
        table_name="cw_worker_claims",
    )
    op.drop_index(
        "cw_worker_claims_worker_state_claimed",
        table_name="cw_worker_claims",
    )
    op.drop_table("cw_worker_claims")
