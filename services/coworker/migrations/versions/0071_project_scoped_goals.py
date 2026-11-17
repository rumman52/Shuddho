"""Bind persistent goals to an optional owner-owned project."""
from alembic import op
import sqlalchemy as sa

revision = "0071_project_scoped_goals"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cw_personal_goals",
        sa.Column("project_id", sa.String(length=36), nullable=True),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_cw_personal_goals_project_owner",
            "cw_personal_goals",
            "cw_projects",
            ["project_id", "owner_id"],
            ["id", "owner_id"],
        )
    op.create_index(
        "cw_personal_goals_owner_project_state",
        "cw_personal_goals",
        ["owner_id", "project_id", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_personal_goals_owner_project_state",
        table_name="cw_personal_goals",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "fk_cw_personal_goals_project_owner",
            "cw_personal_goals",
            type_="foreignkey",
        )
    op.drop_column("cw_personal_goals", "project_id")
