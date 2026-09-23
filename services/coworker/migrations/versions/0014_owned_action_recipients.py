"""owner-scoped action recipient shortcuts

Revision: 0014
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_action_recipients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_key", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("email_key", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name_key", name="uq_cw_action_recipients_owner_name"),
        sa.UniqueConstraint("owner_id", "email_key", name="uq_cw_action_recipients_owner_email"),
    )
    op.create_index("ix_cw_action_recipients_owner_id", "cw_action_recipients", ["owner_id"])
    op.create_index("cw_action_recipients_owner_name", "cw_action_recipients", ["owner_id", "name_key"])


def downgrade():
    op.drop_index("cw_action_recipients_owner_name", table_name="cw_action_recipients")
    op.drop_index("ix_cw_action_recipients_owner_id", table_name="cw_action_recipients")
    op.drop_table("cw_action_recipients")
