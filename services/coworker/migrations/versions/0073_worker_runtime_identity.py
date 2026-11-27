"""Bind worker registrations to immutable build, schema and runtime identity.

Revision ID: 0073_worker_runtime_identity
Revises: 0072_merge_0071_heads
"""
from alembic import op
import sqlalchemy as sa

revision = "0073_worker_runtime_identity"
down_revision = "0072_merge_0071_heads"
branch_labels = None
depends_on = None

SCHEMA = "shuddho_coworker"
TABLE = "cw_worker_instances"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("build_digest", sa.String(length=64), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("schema_revision", sa.String(length=128), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("model_provider", sa.String(length=32), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("model_id", sa.String(length=160), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("runtime_identity_sha256", sa.String(length=64), nullable=True), schema=SCHEMA)

    if op.get_bind().dialect.name != "postgresql":
        return

    op.create_check_constraint(
        "ck_cw_worker_instances_runtime_identity",
        TABLE,
        """
        (
            build_digest IS NULL
            AND schema_revision IS NULL
            AND model_provider IS NULL
            AND model_id IS NULL
            AND runtime_identity_sha256 IS NULL
        )
        OR
        (
            build_digest ~ '^[0-9a-f]{64}$'
            AND schema_revision ~ '^[A-Za-z0-9_]{1,128}$'
            AND model_provider IN ('deepseek', 'gemma')
            AND model_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$'
            AND runtime_identity_sha256 ~ '^[0-9a-f]{64}$'
        )
        """,
        schema=SCHEMA,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION shuddho_coworker.cw_enforce_worker_registration_revision()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
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

            IF current_setting('shuddho.worker_task_queue', true) IS DISTINCT FROM NEW.task_queue
               OR current_setting('shuddho.worker_build_digest', true) IS DISTINCT FROM NEW.build_digest
               OR current_setting('shuddho.worker_schema_revision', true) IS DISTINCT FROM NEW.schema_revision
               OR current_setting('shuddho.worker_model_provider', true) IS DISTINCT FROM NEW.model_provider
               OR current_setting('shuddho.worker_model_id', true) IS DISTINCT FROM NEW.model_id
               OR current_setting('shuddho.worker_runtime_identity_sha256', true)
                    IS DISTINCT FROM NEW.runtime_identity_sha256 THEN
                RAISE EXCEPTION
                    'worker registration requires matching deployment-attested runtime identity'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION shuddho_coworker.cw_enforce_worker_runtime_identity_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF ROW(
                NEW.task_queue, NEW.source_revision, NEW.build_digest,
                NEW.schema_revision, NEW.model_provider, NEW.model_id,
                NEW.runtime_identity_sha256
            ) IS DISTINCT FROM ROW(
                OLD.task_queue, OLD.source_revision, OLD.build_digest,
                OLD.schema_revision, OLD.model_provider, OLD.model_id,
                OLD.runtime_identity_sha256
            ) THEN
                RAISE EXCEPTION
                    'worker runtime identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER cw_worker_runtime_identity_immutable_guard
        BEFORE UPDATE OF task_queue, source_revision, build_digest, schema_revision,
            model_provider, model_id, runtime_identity_sha256
        ON shuddho_coworker.cw_worker_instances
        FOR EACH ROW
        EXECUTE FUNCTION shuddho_coworker.cw_enforce_worker_runtime_identity_immutable();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS cw_worker_runtime_identity_immutable_guard "
            "ON shuddho_coworker.cw_worker_instances"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS shuddho_coworker.cw_enforce_worker_runtime_identity_immutable()"
        )
        # Restore the 0070-pinned source-revision-only guard. The old trigger
        # remains in place and continues to protect legacy deployments.
        op.execute(
            """
            CREATE OR REPLACE FUNCTION shuddho_coworker.cw_enforce_worker_registration_revision()
            RETURNS trigger
            LANGUAGE plpgsql
            SET search_path = pg_catalog
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
        op.drop_constraint(
            "ck_cw_worker_instances_runtime_identity", TABLE, schema=SCHEMA, type_="check",
        )
    for name in (
        "runtime_identity_sha256", "model_id", "model_provider",
        "schema_revision", "build_digest",
    ):
        op.drop_column(TABLE, name, schema=SCHEMA)
