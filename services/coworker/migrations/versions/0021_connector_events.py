"""PA-06 Google connector subscriptions and event intake.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_connector_subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("grant_id", sa.String(length=36), sa.ForeignKey("cw_connector_read_grants.id"), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("cw_connections.id"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("provider_subscription_id", sa.String(length=512)),
        sa.Column("provider_resource_id", sa.String(length=512)),
        sa.Column("token_hash", sa.String(length=64)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("renew_after", sa.DateTime(timezone=True)),
        sa.Column("claim_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=60)),
        sa.Column("last_event_sequence", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("grant_id", "generation", name="uq_cw_connector_subscriptions_grant_generation"),
    )
    op.create_index("ix_cw_connector_subscriptions_owner_id", "cw_connector_subscriptions", ["owner_id"])
    op.create_index("ix_cw_connector_subscriptions_grant_id", "cw_connector_subscriptions", ["grant_id"])
    op.create_index("ix_cw_connector_subscriptions_connection_id", "cw_connector_subscriptions", ["connection_id"])
    op.create_index("cw_connector_subscriptions_owner_state", "cw_connector_subscriptions", ["owner_id", "state"])
    op.create_index("cw_connector_subscriptions_grant_state", "cw_connector_subscriptions", ["grant_id", "state"])
    op.create_index("cw_connector_subscriptions_due", "cw_connector_subscriptions", ["state", "renew_after"])
    op.create_index("cw_connector_subscriptions_provider_id", "cw_connector_subscriptions", ["provider", "provider_subscription_id"])

    op.create_table(
        "cw_connector_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("grant_id", sa.String(length=36), sa.ForeignKey("cw_connector_read_grants.id"), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), sa.ForeignKey("cw_connector_subscriptions.id"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("capability", sa.String(length=30), nullable=False),
        sa.Column("provider_event_id", sa.String(length=256), nullable=False),
        sa.Column("provider_sequence", sa.String(length=64)),
        sa.Column("provider_cursor_hint", sa.String(length=1024)),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_until", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=60)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("subscription_id", "provider_event_id", name="uq_cw_connector_events_subscription_event"),
    )
    op.create_index("ix_cw_connector_events_owner_id", "cw_connector_events", ["owner_id"])
    op.create_index("ix_cw_connector_events_grant_id", "cw_connector_events", ["grant_id"])
    op.create_index("ix_cw_connector_events_subscription_id", "cw_connector_events", ["subscription_id"])
    op.create_index("cw_connector_events_owner_state", "cw_connector_events", ["owner_id", "state"])
    op.create_index("cw_connector_events_grant_state", "cw_connector_events", ["grant_id", "state"])
    op.create_index("cw_connector_events_available", "cw_connector_events", ["state", "available_at"])


def downgrade():
    op.drop_table("cw_connector_events")
    op.drop_table("cw_connector_subscriptions")
