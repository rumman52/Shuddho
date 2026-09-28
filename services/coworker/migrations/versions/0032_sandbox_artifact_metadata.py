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
    # SQLite is used by the isolated Coworker test suite. Batch mode recreates
    # the table there while emitting compatible ALTER operations on PostgreSQL.
    with op.batch_alter_table("cw_artifacts") as batch_op:
        batch_op.alter_column(
            "task_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("sandbox_execution_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "artifact_class",
                sa.String(length=30),
                nullable=False,
                server_default="task_output",
            )
        )
        batch_op.add_column(
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_cw_artifacts_sandbox_execution",
            "cw_sandbox_executions",
            ["sandbox_execution_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_cw_artifacts_sandbox_execution_id",
            ["sandbox_execution_id"],
        )
        batch_op.create_index(
            "cw_artifacts_owner_class_expiry",
            ["owner_id", "artifact_class", "expires_at"],
        )
        batch_op.create_unique_constraint(
            "uq_cw_artifacts_sandbox_execution_filename",
            ["sandbox_execution_id", "filename"],
        )


def downgrade():
    # Do not destroy sandbox artifacts on application rollback. The supported
    # rollback is code/flag rollback with this additive schema retained.
    raise RuntimeError(
        "0032 is expand-only; roll back the application/flag without downgrading this schema"
    )
