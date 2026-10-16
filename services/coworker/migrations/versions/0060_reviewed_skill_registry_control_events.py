"""CW-11 append-only reviewed-skill registry control audit events.

Revision ID: 0060
Revises: 0059
"""
from alembic import op
import sqlalchemy as sa

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_reviewed_skill_registry_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_name", sa.String(60), nullable=False),
        sa.Column(
            "publication_id",
            sa.String(36),
            sa.ForeignKey(
                "cw_reviewed_skill_publications.id",
                name="fk_cw_reviewed_skill_registry_events_publication_id",
            ),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("actor_reference", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "cw_reviewed_skill_registry_events_skill_created",
        "cw_reviewed_skill_registry_events",
        ["skill_name", "created_at"],
    )
    op.create_index(
        "cw_reviewed_skill_registry_events_publication",
        "cw_reviewed_skill_registry_events",
        ["publication_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_reviewed_skill_registry_events_publication",
        table_name="cw_reviewed_skill_registry_events",
    )
    op.drop_index(
        "cw_reviewed_skill_registry_events_skill_created",
        table_name="cw_reviewed_skill_registry_events",
    )
    op.drop_table("cw_reviewed_skill_registry_events")
