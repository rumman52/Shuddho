"""PA-07 secure takeover credential handoff.

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_browser_sessions", sa.Column("takeover_reason", sa.String(length=30)))
    op.add_column("cw_browser_commands", sa.Column("secret_sealed", sa.Text()))


def downgrade():
    op.drop_column("cw_browser_commands", "secret_sealed")
    op.drop_column("cw_browser_sessions", "takeover_reason")
