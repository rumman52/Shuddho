"""PA-10 proactive Meeting Coworker exact source and recovery identity.

Revision ID: 0041
Revises: 0040

Freeze exact connected snapshot scope onto a bounded Agent run and retain the
calendar snapshot/start identity on each admitted meeting occurrence so process
loss, cancellation and reschedule recovery stay deterministic.
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_agent_runs",
        sa.Column(
            "connector_snapshot_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    with op.batch_alter_table("cw_automation_occurrences") as batch_op:
        batch_op.add_column(
            sa.Column("trigger_snapshot_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("trigger_start_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_cw_automation_occurrences_trigger_snapshot_id",
            "cw_connector_snapshots",
            ["trigger_snapshot_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_cw_automation_occurrences_trigger_snapshot",
            ["trigger_snapshot_id"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "0041 is expand-only; roll back application/flags without downgrading meeting recovery evidence"
    )
