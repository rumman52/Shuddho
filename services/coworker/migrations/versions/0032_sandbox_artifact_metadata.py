"""PA-08 sandbox artifact metadata.

Revision ID: 0032
Revises: 0031

This is an additive expand migration. Runtime rollback is performed by
disabling SHUDDHO_CODE_EXECUTION_ENABLED and deploying the previous code while
leaving these nullable columns in place so existing artifacts are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "cw_artifacts",
        "task_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.add_column(
        "cw_artifacts",
        sa.Column("sandbox_execution_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "cw_artifacts",
        sa.Column(
            "artifact_class",
            sa.String(length=30),
            nullable=False,
            server_default="task_output",
        ),
    )
    op.add_column(
        "cw_artifacts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cw_artifacts_sandbox_execution",
        "cw_artifacts",
        "cw_sandbox_executions",
        ["sandbox_execution_id"],
        ["id"],
    )
    op.create_index(
        "ix_cw_artifacts_sandbox_execution_id",
        "cw_artifacts",
        ["sandbox_execution_id"],
    )
    op.create_index(
        "cw_artifacts_owner_class_expiry",
        "cw_artifacts",
        ["owner_id", "artifact_class", "expires_at"],
    )
    op.create_unique_constraint(
        "uq_cw_artifacts_sandbox_execution_filename",
        "cw_artifacts",
        ["sandbox_execution_id", "filename"],
    )


def downgrade():
    # Do not destroy sandbox artifacts on application rollback. The supported
    # rollback is code/flag rollback with this additive schema retained.
    raise RuntimeError(
        "0032 is expand-only; roll back the application/flag without downgrading this schema"
    )
