"""PA-07 encrypted browser session continuity.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_browser_sessions", sa.Column("storage_state_sealed", sa.Text()))
    op.add_column(
        "cw_browser_sessions",
        sa.Column("storage_state_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cw_browser_sessions",
        sa.Column("storage_state_updated_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_column("cw_browser_sessions", "storage_state_updated_at")
    op.drop_column("cw_browser_sessions", "storage_state_version")
    op.drop_column("cw_browser_sessions", "storage_state_sealed")
