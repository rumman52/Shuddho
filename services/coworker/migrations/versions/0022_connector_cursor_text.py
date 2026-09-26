"""PA-06 opaque provider delta cursors.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite (used by the isolated Coworker test suite) cannot execute
    # ALTER TABLE ... ALTER COLUMN ... TYPE directly. Alembic batch mode
    # recreates/copies the table on SQLite while emitting a normal ALTER on
    # PostgreSQL, so the same migration is portable across test and production.
    with op.batch_alter_table("cw_connector_cursors") as batch_op:
        batch_op.alter_column(
            "cursor",
            existing_type=sa.String(length=1024),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("cw_connector_cursors") as batch_op:
        batch_op.alter_column(
            "cursor",
            existing_type=sa.Text(),
            type_=sa.String(length=1024),
            existing_nullable=True,
        )
