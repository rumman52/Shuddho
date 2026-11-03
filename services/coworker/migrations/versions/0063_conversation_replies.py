"""Add an optional stored assistant reply to user messages.
Revision ID: 0063
Revises: 0062
"""
from alembic import op
import sqlalchemy as sa
revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("cw_conversation_messages", sa.Column("assistant_reply", sa.JSON(), nullable=True))

def downgrade():
    op.drop_column("cw_conversation_messages", "assistant_reply")
