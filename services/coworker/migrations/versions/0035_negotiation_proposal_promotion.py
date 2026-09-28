"""Bind reviewable PA-09 proposals to promoted action previews.

Revision ID: 0035
Revises: 0034
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cw_negotiation_proposals") as batch_op:
        batch_op.add_column(
            sa.Column("promoted_action_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_cw_negotiation_proposals_promoted_action",
            "cw_external_actions",
            ["promoted_action_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_cw_negotiation_proposals_promoted_action",
            ["promoted_action_id"],
        )
        batch_op.create_index(
            "ix_cw_negotiation_proposals_promoted_action_id",
            ["promoted_action_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("cw_negotiation_proposals") as batch_op:
        batch_op.drop_index("ix_cw_negotiation_proposals_promoted_action_id")
        batch_op.drop_constraint(
            "uq_cw_negotiation_proposals_promoted_action",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_cw_negotiation_proposals_promoted_action",
            type_="foreignkey",
        )
        batch_op.drop_column("promoted_at")
        batch_op.drop_column("promoted_action_id")
