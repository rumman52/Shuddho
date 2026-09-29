"""Bind durable in-app notifications to stable PA-10 source identities.

Revision ID: 0036
Revises: 0035
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cw_notifications") as batch_op:
        batch_op.add_column(sa.Column("source_kind", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("source_id", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            "uq_cw_notifications_owner_source",
            ["owner_id", "source_kind", "source_id"],
        )


def downgrade():
    with op.batch_alter_table("cw_notifications") as batch_op:
        batch_op.drop_constraint("uq_cw_notifications_owner_source", type_="unique")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source_kind")
