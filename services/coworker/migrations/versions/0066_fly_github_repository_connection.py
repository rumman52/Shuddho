"""Owner-scoped GitHub App installation and Fly repository bindings.

Revision ID: 0066
Revises: 0065
"""
from alembic import op
import sqlalchemy as sa


revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_github_connect_attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("code_verifier_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("user_access_token_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("github_user_id", sa.BigInteger(), nullable=True),
        sa.Column("github_login", sa.String(length=39), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["cw_projects.id", "cw_projects.owner_id"],
            name="fk_cw_github_attempt_project_owner",
        ),
        sa.CheckConstraint(
            "stage IN ('oauth', 'oauth_processing', 'awaiting_install', 'install_processing', 'consumed')",
            name="ck_cw_github_attempt_stage",
        ),
    )
    op.create_index(
        "cw_github_connect_attempts_owner_created",
        "cw_github_connect_attempts",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "cw_github_connect_attempts_expiry",
        "cw_github_connect_attempts",
        ["stage", "expires_at"],
    )

    op.create_table(
        "cw_github_installations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("github_user_id", sa.BigInteger(), nullable=False),
        sa.Column("github_login", sa.String(length=39), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("user_token_bundle_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "installation_id",
            name="uq_cw_github_install_owner_install",
        ),
        sa.UniqueConstraint("id", "owner_id", name="uq_cw_github_install_id_owner"),
    )
    op.create_index(
        "cw_github_install_owner_active",
        "cw_github_installations",
        ["owner_id", "active"],
    )

    op.create_table(
        "cw_github_repository_bindings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("installation_record_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "owner_id"],
            ["cw_projects.id", "cw_projects.owner_id"],
            name="fk_cw_github_binding_project_owner",
        ),
        sa.ForeignKeyConstraint(
            ["installation_record_id", "owner_id"],
            ["cw_github_installations.id", "cw_github_installations.owner_id"],
            name="fk_cw_github_binding_installation_owner",
        ),
        sa.UniqueConstraint(
            "owner_id", "project_id",
            name="uq_cw_github_binding_owner_project",
        ),
    )
    op.create_index(
        "cw_github_binding_owner_project",
        "cw_github_repository_bindings",
        ["owner_id", "project_id", "active"],
    )


def downgrade():
    op.drop_index("cw_github_binding_owner_project", table_name="cw_github_repository_bindings")
    op.drop_table("cw_github_repository_bindings")
    op.drop_index("cw_github_install_owner_active", table_name="cw_github_installations")
    op.drop_table("cw_github_installations")
    op.drop_index("cw_github_connect_attempts_expiry", table_name="cw_github_connect_attempts")
    op.drop_index("cw_github_connect_attempts_owner_created", table_name="cw_github_connect_attempts")
    op.drop_table("cw_github_connect_attempts")
