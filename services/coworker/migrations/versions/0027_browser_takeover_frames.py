"""PA-07 encrypted visual takeover frames.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_browser_sessions", sa.Column("takeover_frame_sealed", sa.Text()))
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_frame_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_frame_content_type", sa.String(length=32)),
    )
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_frame_byte_size", sa.Integer()),
    )
    op.add_column(
        "cw_browser_sessions",
        sa.Column("takeover_frame_updated_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_column("cw_browser_sessions", "takeover_frame_updated_at")
    op.drop_column("cw_browser_sessions", "takeover_frame_byte_size")
    op.drop_column("cw_browser_sessions", "takeover_frame_content_type")
    op.drop_column("cw_browser_sessions", "takeover_frame_version")
    op.drop_column("cw_browser_sessions", "takeover_frame_sealed")
