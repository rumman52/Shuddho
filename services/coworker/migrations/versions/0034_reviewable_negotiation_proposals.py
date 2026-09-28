"""PA-09 reviewable negotiation proposals.

Revision ID: 0034
Revises: 0033
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_negotiation_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("case_revision", sa.Integer(), nullable=False),
        sa.Column("history_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("output_language", sa.String(length=35), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("risk_notes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="suggested"),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cw_negotiation_cases.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["cw_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_cw_negotiation_proposals_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_cw_negotiation_proposals_case_id",
        "cw_negotiation_proposals",
        ["case_id"],
    )
    op.create_index(
        "ix_cw_negotiation_proposals_owner_id",
        "cw_negotiation_proposals",
        ["owner_id"],
    )
    op.create_index(
        "cw_negotiation_proposals_owner_case_created",
        "cw_negotiation_proposals",
        ["owner_id", "case_id", "created_at"],
    )
    op.create_index(
        "cw_negotiation_proposals_case_state",
        "cw_negotiation_proposals",
        ["case_id", "state"],
    )


def downgrade():
    op.drop_index(
        "cw_negotiation_proposals_case_state",
        table_name="cw_negotiation_proposals",
    )
    op.drop_index(
        "cw_negotiation_proposals_owner_case_created",
        table_name="cw_negotiation_proposals",
    )
    op.drop_index(
        "ix_cw_negotiation_proposals_owner_id",
        table_name="cw_negotiation_proposals",
    )
    op.drop_index(
        "ix_cw_negotiation_proposals_case_id",
        table_name="cw_negotiation_proposals",
    )
    op.drop_table("cw_negotiation_proposals")
