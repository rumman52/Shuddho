from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_browser_push_subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("subscription_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "endpoint_hash", name="uq_cw_browser_push_owner_endpoint"),
    )
    op.create_index(
        "ix_cw_browser_push_owner_active",
        "cw_browser_push_subscriptions",
        ["owner_id", "active"],
    )
    op.create_table(
        "cw_browser_push_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("notification_id", sa.String(length=36), sa.ForeignKey("cw_notifications.id"), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), sa.ForeignKey("cw_browser_push_subscriptions.id"), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("notification_id", "subscription_id", name="uq_cw_browser_push_notice_subscription"),
    )
    op.create_index(
        "ix_cw_browser_push_delivery_owner_state",
        "cw_browser_push_deliveries",
        ["owner_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_cw_browser_push_delivery_owner_state", table_name="cw_browser_push_deliveries")
    op.drop_table("cw_browser_push_deliveries")
    op.drop_index("ix_cw_browser_push_owner_active", table_name="cw_browser_push_subscriptions")
    op.drop_table("cw_browser_push_subscriptions")
