from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_agent_runs",
        sa.Column("tool_allowlist", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "cw_automations",
        sa.Column("run_profile", sa.String(length=30), nullable=False, server_default="goal"),
    )
    op.add_column(
        "cw_automations",
        sa.Column("connector_read_grant_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("cw_automations", "connector_read_grant_ids")
    op.drop_column("cw_automations", "run_profile")
    op.drop_column("cw_agent_runs", "tool_allowlist")
