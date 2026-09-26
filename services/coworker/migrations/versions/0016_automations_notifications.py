"""personal-agent automations, occurrence dedupe and durable notifications

Revision: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_automations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("goal_id", sa.String(length=36), nullable=False),
        sa.Column("goal_revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("output_language", sa.String(length=35), nullable=False, server_default="en"),
        sa.Column("overlap_policy", sa.String(length=30), nullable=False, server_default="skip"),
        sa.Column("catchup_window_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("quiet_hours", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_applied_revision", sa.Integer(), nullable=True),
        sa.Column("schedule_applied_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["cw_personal_goals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_automations_owner_idempotency"),
    )
    op.create_index("ix_cw_automations_owner_id", "cw_automations", ["owner_id"])
    op.create_index("ix_cw_automations_workspace_id", "cw_automations", ["workspace_id"])
    op.create_index("ix_cw_automations_goal_id", "cw_automations", ["goal_id"])
    op.create_index("cw_automations_owner_created", "cw_automations", ["owner_id", "created_at"])
    op.create_index("cw_automations_workspace_state", "cw_automations", ["workspace_id", "state"])

    op.create_table(
        "cw_automation_revisions",
        sa.Column("automation_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["automation_id"], ["cw_automations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("automation_id", "revision"),
    )
    op.create_index("ix_cw_automation_revisions_owner_id", "cw_automation_revisions", ["owner_id"])
    op.create_index("cw_automation_revisions_owner_automation", "cw_automation_revisions", ["owner_id", "automation_id"])

    op.create_table(
        "cw_automation_schedule_outbox",
        sa.Column("automation_id", sa.String(length=36), nullable=False),
        sa.Column("desired_revision", sa.Integer(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["automation_id"], ["cw_automations.id"]),
        sa.PrimaryKeyConstraint("automation_id"),
    )
    op.create_index("ix_cw_automation_schedule_outbox_delivered", "cw_automation_schedule_outbox", ["delivered"])

    op.create_table(
        "cw_automation_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("automation_id", sa.String(length=36), nullable=False),
        sa.Column("automation_revision", sa.Integer(), nullable=False),
        sa.Column("occurrence_key", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["automation_id"], ["cw_automations.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("automation_id", "occurrence_key", name="uq_cw_automation_occurrence_key"),
    )
    op.create_index("ix_cw_automation_occurrences_owner_id", "cw_automation_occurrences", ["owner_id"])
    op.create_index("ix_cw_automation_occurrences_automation_id", "cw_automation_occurrences", ["automation_id"])
    op.create_index("ix_cw_automation_occurrences_run_id", "cw_automation_occurrences", ["run_id"])
    op.create_index("cw_automation_occurrences_owner_due", "cw_automation_occurrences", ["owner_id", "due_at"])

    op.create_table(
        "cw_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("automation_id", sa.String(length=36), nullable=True),
        sa.Column("occurrence_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("visible_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["cw_workspaces.id"]),
        sa.ForeignKeyConstraint(["automation_id"], ["cw_automations.id"]),
        sa.ForeignKeyConstraint(["occurrence_id"], ["cw_automation_occurrences.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("occurrence_id", name="uq_cw_notifications_occurrence"),
    )
    op.create_index("ix_cw_notifications_owner_id", "cw_notifications", ["owner_id"])
    op.create_index("ix_cw_notifications_automation_id", "cw_notifications", ["automation_id"])
    op.create_index("cw_notifications_owner_state_visible", "cw_notifications", ["owner_id", "state", "visible_at"])

    op.create_table(
        "cw_notification_outbox",
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["notification_id"], ["cw_notifications.id"]),
        sa.PrimaryKeyConstraint("notification_id"),
    )
    op.create_index("ix_cw_notification_outbox_delivered", "cw_notification_outbox", ["delivered"])


def downgrade():
    op.drop_index("ix_cw_notification_outbox_delivered", table_name="cw_notification_outbox")
    op.drop_table("cw_notification_outbox")
    op.drop_index("cw_notifications_owner_state_visible", table_name="cw_notifications")
    op.drop_index("ix_cw_notifications_automation_id", table_name="cw_notifications")
    op.drop_index("ix_cw_notifications_owner_id", table_name="cw_notifications")
    op.drop_table("cw_notifications")
    op.drop_index("cw_automation_occurrences_owner_due", table_name="cw_automation_occurrences")
    op.drop_index("ix_cw_automation_occurrences_run_id", table_name="cw_automation_occurrences")
    op.drop_index("ix_cw_automation_occurrences_automation_id", table_name="cw_automation_occurrences")
    op.drop_index("ix_cw_automation_occurrences_owner_id", table_name="cw_automation_occurrences")
    op.drop_table("cw_automation_occurrences")
    op.drop_index("ix_cw_automation_schedule_outbox_delivered", table_name="cw_automation_schedule_outbox")
    op.drop_table("cw_automation_schedule_outbox")
    op.drop_index("cw_automation_revisions_owner_automation", table_name="cw_automation_revisions")
    op.drop_index("ix_cw_automation_revisions_owner_id", table_name="cw_automation_revisions")
    op.drop_table("cw_automation_revisions")
    op.drop_index("cw_automations_workspace_state", table_name="cw_automations")
    op.drop_index("cw_automations_owner_created", table_name="cw_automations")
    op.drop_index("ix_cw_automations_goal_id", table_name="cw_automations")
    op.drop_index("ix_cw_automations_workspace_id", table_name="cw_automations")
    op.drop_index("ix_cw_automations_owner_id", table_name="cw_automations")
    op.drop_table("cw_automations")
