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
    # Keep the database default for backward compatibility with any older
    # API/worker binary still draining during a coordinated rollout. SQLite
    # also cannot DROP DEFAULT with PostgreSQL's ALTER COLUMN syntax.


def downgrade():
    op.drop_column("cw_oauth_attempts", "provider")
