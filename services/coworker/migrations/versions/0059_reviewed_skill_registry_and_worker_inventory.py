"""CW-11 trusted reviewed-skill publication/selection and worker inventory.

Revision ID: 0059
Revises: 0058
"""
from alembic import op
import sqlalchemy as sa

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_reviewed_skill_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_name", sa.String(60), nullable=False),
        sa.Column("publication_version", sa.String(80), nullable=False),
        sa.Column("task_workflow_version", sa.String(80), nullable=False),
        sa.Column("manifest_version", sa.String(80), nullable=False),
        sa.Column("review_sha256", sa.String(64), nullable=False),
        sa.Column("publication_sha256", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.String(40), nullable=False),
        sa.Column("tool_names", sa.JSON(), nullable=False),
        sa.Column("resource_limits", sa.JSON(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("rollback_target_version", sa.String(80), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="published"),
        sa.Column("published_by", sa.String(200), nullable=False, server_default="operator"),
        sa.Column("publication_reason", sa.String(500), nullable=False, server_default="reviewed publication"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "skill_name",
            "publication_version",
            name="uq_cw_reviewed_skill_publication_version",
        ),
    )
    op.create_index(
        "cw_reviewed_skill_publications_skill_state",
        "cw_reviewed_skill_publications",
        ["skill_name", "state"],
    )

    op.create_table(
        "cw_reviewed_skill_selections",
        sa.Column("skill_name", sa.String(60), primary_key=True),
        sa.Column(
            "publication_id",
            sa.String(36),
            sa.ForeignKey(
                "cw_reviewed_skill_publications.id",
                name="fk_cw_reviewed_skill_selections_publication_id",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(20), nullable=False, server_default="selected"),
        sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cw_worker_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_queue", sa.String(160), nullable=False),
        sa.Column("source_revision", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="starting"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drain_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drain_requested_by", sa.String(200), nullable=True),
        sa.Column("drain_reason", sa.String(500), nullable=True),
        sa.Column("drained_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "cw_worker_instances_queue_state_heartbeat",
        "cw_worker_instances",
        ["task_queue", "state", "heartbeat_at"],
    )
    op.create_index(
        "cw_worker_instances_revision_state",
        "cw_worker_instances",
        ["source_revision", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_worker_instances_revision_state",
        table_name="cw_worker_instances",
    )
    op.drop_index(
        "cw_worker_instances_queue_state_heartbeat",
        table_name="cw_worker_instances",
    )
    op.drop_table("cw_worker_instances")
    op.drop_table("cw_reviewed_skill_selections")
    op.drop_index(
        "cw_reviewed_skill_publications_skill_state",
        table_name="cw_reviewed_skill_publications",
    )
    op.drop_table("cw_reviewed_skill_publications")
