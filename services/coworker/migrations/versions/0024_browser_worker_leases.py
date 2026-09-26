"""PA-07 durable browser worker command leasing.

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cw_browser_commands", sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("cw_browser_commands", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cw_browser_commands", sa.Column("claimed_by", sa.String(length=64)))
    op.add_column("cw_browser_commands", sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.add_column("cw_browser_commands", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.create_index("cw_browser_commands_state_lease", "cw_browser_commands", ["state", "lease_until"])


def downgrade():
    op.drop_index("cw_browser_commands_state_lease", table_name="cw_browser_commands")
    op.drop_column("cw_browser_commands", "started_at")
    op.drop_column("cw_browser_commands", "lease_until")
    op.drop_column("cw_browser_commands", "claimed_by")
    op.drop_column("cw_browser_commands", "attempts")
    op.drop_column("cw_browser_commands", "result")
