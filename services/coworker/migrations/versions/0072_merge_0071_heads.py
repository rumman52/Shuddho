"""Merge the two independent 0071 migration branches.

Both migrations follow 0070 and change different tables.  This revision has
no DDL: Alembic must apply both parents before recording the unified head.
Do not rewrite, delete, or renumber either already-published revision.
"""

revision = "0072_merge_0071_heads"
down_revision = ("0071", "0071_project_scoped_goals")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
