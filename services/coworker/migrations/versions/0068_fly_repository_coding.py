"""Persist Fly workspace manifests and immutable repository patch decisions.

Revision ID: 0068_fly_repository_coding
Revises: 0067_agent_decision_latency
"""
from alembic import op
import sqlalchemy as sa


revision = "0068_fly_repository_coding"
down_revision = "0067_agent_decision_latency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cw_fly_workspace_manifests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id", "owner_id"], ["cw_projects.id", "cw_projects.owner_id"]),
        sa.UniqueConstraint("owner_id", "project_id", name="uq_cw_fly_workspace_owner_project"),
    )
    op.create_index(
        "cw_fly_workspace_owner_project_revision",
        "cw_fly_workspace_manifests",
        ["owner_id", "project_id", "revision"],
    )

    op.create_table(
        "cw_fly_patch_proposals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("base_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("base_commit_sha", sa.String(length=40), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("file_summaries", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("patch_object_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("patch_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("patch_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("review_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="generating"),
        sa.Column("repair_of_execution_id", sa.String(length=36), nullable=True),
        sa.Column("repair_root_proposal_id", sa.String(length=36), nullable=True),
        sa.Column("repair_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
        sa.Column("applied_manifest_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id", "owner_id"], ["cw_projects.id", "cw_projects.owner_id"]),
        sa.UniqueConstraint("owner_id", "project_id", "idempotency_key", name="uq_cw_fly_patch_owner_project_key"),
    )
    op.create_index(
        "cw_fly_patch_owner_project_state",
        "cw_fly_patch_proposals",
        ["owner_id", "project_id", "state", "created_at"],
    )
    op.create_index(
        "cw_fly_patch_repair_root",
        "cw_fly_patch_proposals",
        ["owner_id", "project_id", "repair_root_proposal_id"],
    )

    op.create_table(
        "cw_fly_patch_reviews",
        sa.Column("proposal_id", sa.String(length=36), sa.ForeignKey("cw_fly_patch_proposals.id"), primary_key=True),
        sa.Column("owner_id", sa.String(length=64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("review_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id", "owner_id"], ["cw_projects.id", "cw_projects.owner_id"]),
    )
    op.create_index(
        "cw_fly_patch_reviews_owner_project",
        "cw_fly_patch_reviews",
        ["owner_id", "project_id", "decision"],
    )

    op.add_column("cw_sandbox_executions", sa.Column("fly_project_id", sa.String(length=36), nullable=True))
    op.add_column("cw_sandbox_executions", sa.Column("fly_workspace_revision", sa.Integer(), nullable=True))
    op.add_column("cw_sandbox_executions", sa.Column("fly_manifest_sha256", sa.String(length=64), nullable=True))
    op.add_column("cw_sandbox_executions", sa.Column("fly_patch_proposal_id", sa.String(length=36), nullable=True))
    op.add_column("cw_sandbox_executions", sa.Column("fly_request_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_cw_sandbox_executions_fly_project_id", "cw_sandbox_executions", ["fly_project_id"])
    op.create_index("ix_cw_sandbox_executions_fly_patch_proposal_id", "cw_sandbox_executions", ["fly_patch_proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_cw_sandbox_executions_fly_patch_proposal_id", table_name="cw_sandbox_executions")
    op.drop_index("ix_cw_sandbox_executions_fly_project_id", table_name="cw_sandbox_executions")
    op.drop_column("cw_sandbox_executions", "fly_patch_proposal_id")
    op.drop_column("cw_sandbox_executions", "fly_request_fingerprint")
    op.drop_column("cw_sandbox_executions", "fly_manifest_sha256")
    op.drop_column("cw_sandbox_executions", "fly_workspace_revision")
    op.drop_column("cw_sandbox_executions", "fly_project_id")
    op.drop_index("cw_fly_patch_reviews_owner_project", table_name="cw_fly_patch_reviews")
    op.drop_table("cw_fly_patch_reviews")
    op.drop_index("cw_fly_patch_repair_root", table_name="cw_fly_patch_proposals")
    op.drop_index("cw_fly_patch_owner_project_state", table_name="cw_fly_patch_proposals")
    op.drop_table("cw_fly_patch_proposals")
    op.drop_index("cw_fly_workspace_owner_project_revision", table_name="cw_fly_workspace_manifests")
    op.drop_table("cw_fly_workspace_manifests")
