"""bind oauth attempts to connector provider

Revision: 0012
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cw_oauth_attempts",
        sa.Column(
            "provider",
            sa.String(length=20),
            nullable=False,
            server_default="google",
        ),
    )
    op.alter_column(
        "cw_oauth_attempts",
        "provider",
        server_default=None,
    )


def downgrade():
    op.drop_column("cw_oauth_attempts", "provider")
