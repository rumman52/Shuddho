"""Pin the search path of the PostgreSQL worker registration trigger."""
from alembic import op

revision = "0070"
down_revision = "0069_conversation_task_briefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER FUNCTION cw_enforce_worker_registration_revision() SET search_path TO pg_catalog")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER FUNCTION cw_enforce_worker_registration_revision() RESET search_path")
