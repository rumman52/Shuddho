"""PA-10 goal-driven proactive automation tool scope.

Revision ID: 0043
Revises: 0042

Persist the reviewed non-consequential tool scope on each automation revision so
goal-driven proactive wake-ups cannot expand their own authority.
"""
from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_automations",
        sa.Column(
            "tool_allowlist",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "0043 is expand-only; roll back application/flags without deleting reviewed automation authority"
    )
