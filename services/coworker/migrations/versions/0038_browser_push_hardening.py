from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_cw_browser_push_delivery_pending_created",
        "cw_browser_push_deliveries",
        ["created_at"],
        postgresql_where=sa.text("state = 'pending'"),
        sqlite_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cw_browser_push_delivery_pending_created",
        table_name="cw_browser_push_deliveries",
    )
