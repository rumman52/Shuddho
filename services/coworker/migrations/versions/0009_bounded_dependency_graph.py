"""bounded server-owned dependency graph

Revision: 0009
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_agent_steps",
        sa.Column("depends_on_ordinals", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("cw_agent_steps", "depends_on_ordinals")
