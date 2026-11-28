"""Add immutable runtime identity to worker registrations.

Revision ID: 0073_worker_runtime_identity
Revises: 0072_merge_0071_heads
"""
from alembic import op
import sqlalchemy as sa

revision = "0073_worker_runtime_identity"
down_revision = "0072_merge_0071_heads"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("build_digest", 64),
    ("schema_revision", 32),
    ("model_provider", 32),
    ("model_id", 120),
    ("runtime_identity_sha256", 64),
)


def upgrade() -> None:
    for name, size in _COLUMNS:
        op.add_column("cw_worker_instances", sa.Column(name, sa.String(size), nullable=True))
    if op.get_bind().dialect.name != "postgresql":
        return
    # Existing legacy rows remain readable (all NULL); partial attestations
    # are never valid. New registrations must pass the separate INSERT guard.
    op.create_check_constraint(
        "ck_cw_worker_runtime_identity_complete", "cw_worker_instances",
        "(build_digest IS NULL AND schema_revision IS NULL AND model_provider IS NULL "
        "AND model_id IS NULL AND runtime_identity_sha256 IS NULL) OR "
        "(build_digest IS NOT NULL AND build_digest ~ '^[0-9a-f]{64}$' "
        "AND schema_revision IS NOT NULL AND length(schema_revision) > 0 "
        "AND model_provider IS NOT NULL AND model_provider IN ('deepseek','gemma') "
        "AND model_id IS NOT NULL AND length(model_id) > 0 "
        "AND runtime_identity_sha256 IS NOT NULL AND runtime_identity_sha256 ~ '^[0-9a-f]{64}$')",
    )
    op.execute("""
        CREATE FUNCTION cw_enforce_worker_runtime_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF ROW(OLD.source_revision, OLD.task_queue, OLD.build_digest,
                       OLD.schema_revision, OLD.model_provider, OLD.model_id,
                       OLD.runtime_identity_sha256)
                   IS DISTINCT FROM
                   ROW(NEW.source_revision, NEW.task_queue, NEW.build_digest,
                       NEW.schema_revision, NEW.model_provider, NEW.model_id,
                       NEW.runtime_identity_sha256) THEN
                    RAISE EXCEPTION 'worker runtime identity is immutable' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.source_revision !~ '^[0-9a-f]{40}$'
               OR NEW.build_digest IS NULL OR NEW.schema_revision IS NULL
               OR NEW.model_provider IS NULL OR NEW.model_id IS NULL
               OR NEW.runtime_identity_sha256 IS NULL
               OR NEW.build_digest IS DISTINCT FROM current_setting('shuddho.worker_build_digest', true)
               OR NEW.schema_revision IS DISTINCT FROM current_setting('shuddho.worker_schema_revision', true)
               OR NEW.model_provider IS DISTINCT FROM current_setting('shuddho.worker_model_provider', true)
               OR NEW.model_id IS DISTINCT FROM current_setting('shuddho.worker_model_id', true)
               OR NEW.runtime_identity_sha256 IS DISTINCT FROM current_setting('shuddho.worker_runtime_identity_sha256', true)
               OR NEW.task_queue IS DISTINCT FROM current_setting('shuddho.worker_task_queue', true)
            THEN
                RAISE EXCEPTION 'worker registration requires deployment-attested runtime identity'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    # The existing revision guard sorts before this trigger on INSERT; keep
    # its original semantics, rather than weakening legacy source fencing.
    op.execute("""
        CREATE TRIGGER cw_worker_runtime_identity_guard
        BEFORE INSERT OR UPDATE ON cw_worker_instances
        FOR EACH ROW EXECUTE FUNCTION cw_enforce_worker_runtime_identity();
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER cw_worker_runtime_identity_guard ON cw_worker_instances")
        op.execute("DROP FUNCTION cw_enforce_worker_runtime_identity()")
        op.drop_constraint("ck_cw_worker_runtime_identity_complete", "cw_worker_instances", type_="check")
    for name, _ in reversed(_COLUMNS):
        op.drop_column("cw_worker_instances", name)
