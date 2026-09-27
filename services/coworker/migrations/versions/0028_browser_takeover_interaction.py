"""PA-07 human takeover interaction frame binding.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_frame_sha256", sa.String(length=64)),
    )


def downgrade():
    op.drop_column("cw_browser_sessions", "takeover_frame_sha256")
