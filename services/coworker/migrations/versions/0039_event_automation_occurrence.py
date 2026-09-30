"""PA-10 connected-event automation occurrence identity.

Revision ID: 0039
Revises: 0038

Additive metadata makes an admitted connector event recoverable after a worker
process loss without creating a second event or schedule authority.
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite backs the repository acceptance suite; batch mode recreates the
    # table there while producing compatible ALTER statements on PostgreSQL.
    with op.batch_alter_table("cw_automation_occurrences") as batch_op:
        batch_op.add_column(
            sa.Column("trigger_event_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_cw_automation_occurrences_trigger_event_id",
            "cw_connector_events",
            ["trigger_event_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_cw_automation_occurrences_trigger_event",
            ["trigger_event_id"],
        )


def downgrade() -> None:
    # This is an additive recovery field. Runtime rollback should leave it in
    # place so already-admitted occurrence evidence is not destroyed.
    raise RuntimeError(
        "0039 is expand-only; roll back application/flags without downgrading this schema"
    )
