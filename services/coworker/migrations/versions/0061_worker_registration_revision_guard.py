"""Require deployment-attested worker registration context in PostgreSQL.

Revision ID: 0061
Revises: 0060
"""
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # SQLite remains useful for repository contract tests. Production fleet
        # safety relies on PostgreSQL, where the trigger protects old binaries
        # that do not participate in the application advisory-lock protocol.
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION cw_enforce_worker_registration_revision()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            attested_revision text;
        BEGIN
            attested_revision := current_setting('shuddho.worker_source_revision', true);
            IF attested_revision IS NULL
               OR attested_revision = ''
               OR attested_revision <> NEW.source_revision THEN
                RAISE EXCEPTION
                    'worker registration requires matching deployment-attested source revision'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER cw_worker_registration_revision_guard
        BEFORE INSERT ON cw_worker_instances
        FOR EACH ROW
        EXECUTE FUNCTION cw_enforce_worker_registration_revision();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS cw_worker_registration_revision_guard ON cw_worker_instances")
    op.execute("DROP FUNCTION IF EXISTS cw_enforce_worker_registration_revision()")
