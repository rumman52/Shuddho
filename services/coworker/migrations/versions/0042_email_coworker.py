"""PA-10 proactive Email Coworker event snapshot scope.

Revision ID: 0042
Revises: 0041

Persist the exact connector snapshots changed by each authenticated provider
event so proactive Email Coworker retries cannot silently widen mailbox context.
"""
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_connector_events",
        sa.Column(
            "synced_snapshot_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "0042 is expand-only; roll back application/flags without deleting event evidence"
    )
