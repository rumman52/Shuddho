"""Add private owner-scoped conversations; additive for existing workers."""
from alembic import op
import sqlalchemy as sa

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("message_sequence", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_conversations_owner_key"),
        sa.UniqueConstraint("id", "owner_id", name="uq_cw_conversations_id_owner"),
    )
    op.create_index("ix_cw_conversations_owner_id", "cw_conversations", ["owner_id"])
    op.create_table(
        "cw_conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("client_request_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("selected_sources", sa.JSON(), nullable=False),
        sa.Column("resource_links", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id", "owner_id"], ["cw_conversations.id", "cw_conversations.owner_id"]),
        sa.UniqueConstraint("conversation_id", "client_request_key", name="uq_cw_messages_conversation_key"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_cw_messages_conversation_sequence"),
    )
    op.create_index("ix_cw_conversation_messages_owner_id", "cw_conversation_messages", ["owner_id"])
    op.create_index("ix_cw_conversation_messages_conversation_id", "cw_conversation_messages", ["conversation_id"])


def downgrade():
    op.drop_table("cw_conversation_messages")
    op.drop_table("cw_conversations")
