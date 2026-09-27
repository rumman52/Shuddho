"""PA-07 worker-affine live takeover context.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_worker_ref", sa.String(length=64)),
    )
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_worker_lease_until", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "cw_browser_sessions_takeover_worker_lease",
        "cw_browser_sessions",
        ["takeover_worker_ref", "takeover_worker_lease_until"],
    )


def downgrade():
    op.drop_index(
        "cw_browser_sessions_takeover_worker_lease",
        table_name="cw_browser_sessions",
    )
    op.drop_column("cw_browser_sessions", "takeover_worker_lease_until")
    op.drop_column("cw_browser_sessions", "takeover_worker_ref")
