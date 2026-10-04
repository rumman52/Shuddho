"""TX-05 transaction execution receipt and reconciliation evidence.

Revision ID: 0046
Revises: 0045

The TX-02 execution-link table had no public writer. TX-05 makes that boundary
explicit, one-attempt, hash-bound, and auditable. If unexpected legacy rows are
present, migration fails closed instead of inventing missing binding evidence.
"""
from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


ACTION_STATES = (
    "awaiting_approval",
    "queued",
    "executing",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
    "outcome_unknown",
)


def _action_state_check(column: str) -> str:
    values = ",".join(f"'{value}'" for value in ACTION_STATES)
    return f"{column} IN ({values})"


def upgrade() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        sa.text("SELECT count(*) FROM cw_transaction_execution_links")
    ).scalar_one()
    if int(existing or 0) != 0:
        raise RuntimeError(
            "TX-05 cannot backfill unexpected cw_transaction_execution_links rows; "
            "review and remove or migrate them explicitly before upgrading."
        )

    with op.batch_alter_table("cw_transaction_execution_links") as batch_op:
        batch_op.add_column(sa.Column("terms_revision", sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column("terms_sha256", sa.String(length=64), nullable=False))
        batch_op.add_column(sa.Column("preview_hash", sa.String(length=64), nullable=False))
        batch_op.add_column(sa.Column("provider", sa.String(length=40), nullable=False))
        batch_op.add_column(sa.Column("action_kind", sa.String(length=60), nullable=False))
        batch_op.create_unique_constraint(
            "uq_cw_transaction_execution_links_transaction",
            ["transaction_id"],
        )
        batch_op.create_check_constraint(
            "ck_cw_transaction_execution_links_terms_revision",
            "terms_revision >= 1",
        )
        batch_op.create_check_constraint(
            "ck_cw_transaction_execution_links_terms_sha256",
            "length(terms_sha256) = 64",
        )
        batch_op.create_check_constraint(
            "ck_cw_transaction_execution_links_preview_hash",
            "length(preview_hash) = 64",
        )

    op.create_table(
        "cw_transaction_reconciliation_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transaction_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("external_action_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_revision", sa.Integer(), nullable=False),
        sa.Column("action_state", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("action_kind", sa.String(length=60), nullable=False),
        sa.Column("preview_hash", sa.String(length=64), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=True),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("action_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_cw_transaction_reconciliation_sequence"),
        sa.CheckConstraint(
            "transaction_revision >= 1",
            name="ck_cw_transaction_reconciliation_revision",
        ),
        sa.CheckConstraint(
            _action_state_check("action_state"),
            name="ck_cw_transaction_reconciliation_action_state",
        ),
        sa.CheckConstraint(
            "length(preview_hash) = 64",
            name="ck_cw_transaction_reconciliation_preview_hash",
        ),
        sa.CheckConstraint(
            "receipt_sha256 IS NULL OR length(receipt_sha256) = 64",
            name="ck_cw_transaction_reconciliation_receipt_sha256",
        ),
        sa.CheckConstraint(
            "length(evidence_sha256) = 64",
            name="ck_cw_transaction_reconciliation_evidence_sha256",
        ),
        sa.ForeignKeyConstraint(["external_action_id"], ["cw_external_actions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.ForeignKeyConstraint(
            ["transaction_id", "owner_id"],
            ["cw_transactions.id", "cw_transactions.owner_id"],
            name="fk_cw_transaction_reconciliation_transaction_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            "sequence",
            name="uq_cw_transaction_reconciliation_sequence",
        ),
        sa.UniqueConstraint(
            "external_action_id",
            "evidence_sha256",
            name="uq_cw_transaction_reconciliation_action_evidence",
        ),
    )
    op.create_index(
        "ix_cw_transaction_reconciliation_evidence_transaction_id",
        "cw_transaction_reconciliation_evidence",
        ["transaction_id"],
    )
    op.create_index(
        "ix_cw_transaction_reconciliation_evidence_owner_id",
        "cw_transaction_reconciliation_evidence",
        ["owner_id"],
    )
    op.create_index(
        "ix_cw_transaction_reconciliation_evidence_external_action_id",
        "cw_transaction_reconciliation_evidence",
        ["external_action_id"],
    )
    op.create_index(
        "cw_transaction_reconciliation_owner_transaction_sequence",
        "cw_transaction_reconciliation_evidence",
        ["owner_id", "transaction_id", "sequence"],
    )
    op.create_index(
        "cw_transaction_reconciliation_action_observed",
        "cw_transaction_reconciliation_evidence",
        ["external_action_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "cw_transaction_reconciliation_action_observed",
        table_name="cw_transaction_reconciliation_evidence",
    )
    op.drop_index(
        "cw_transaction_reconciliation_owner_transaction_sequence",
        table_name="cw_transaction_reconciliation_evidence",
    )
    op.drop_index(
        "ix_cw_transaction_reconciliation_evidence_external_action_id",
        table_name="cw_transaction_reconciliation_evidence",
    )
    op.drop_index(
        "ix_cw_transaction_reconciliation_evidence_owner_id",
        table_name="cw_transaction_reconciliation_evidence",
    )
    op.drop_index(
        "ix_cw_transaction_reconciliation_evidence_transaction_id",
        table_name="cw_transaction_reconciliation_evidence",
    )
    op.drop_table("cw_transaction_reconciliation_evidence")

    with op.batch_alter_table("cw_transaction_execution_links") as batch_op:
        batch_op.drop_constraint(
            "ck_cw_transaction_execution_links_preview_hash",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_cw_transaction_execution_links_terms_sha256",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_cw_transaction_execution_links_terms_revision",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_cw_transaction_execution_links_transaction",
            type_="unique",
        )
        batch_op.drop_column("action_kind")
        batch_op.drop_column("provider")
        batch_op.drop_column("preview_hash")
        batch_op.drop_column("terms_sha256")
        batch_op.drop_column("terms_revision")
