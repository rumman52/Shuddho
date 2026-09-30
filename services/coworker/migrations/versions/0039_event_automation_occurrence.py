from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_automation_occurrences",
        sa.Column("trigger_event_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_cw_automation_occurrences_trigger_event_id",
        "cw_automation_occurrences",
        "cw_connector_events",
        ["trigger_event_id"],
        ["id"],
    )
    op.create_index(
        "ix_cw_automation_occurrences_trigger_event",
        "cw_automation_occurrences",
        ["trigger_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cw_automation_occurrences_trigger_event",
        table_name="cw_automation_occurrences",
    )
    op.drop_constraint(
        "fk_cw_automation_occurrences_trigger_event_id",
        "cw_automation_occurrences",
        type_="foreignkey",
    )
    op.drop_column("cw_automation_occurrences", "trigger_event_id")
