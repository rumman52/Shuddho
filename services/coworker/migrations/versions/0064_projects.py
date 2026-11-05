"""Add owner-scoped projects and references to existing workspace resources.
Revision ID: 0064
Revises: 0063
"""
from alembic import op
import sqlalchemy as sa
revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("cw_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_projects_owner_key"),
        sa.UniqueConstraint("id", "owner_id", name="uq_cw_projects_id_owner"))
    op.create_index("ix_cw_projects_owner_id", "cw_projects", ["owner_id"])
    op.create_table("cw_project_resources",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("cw_accounts.id"), nullable=False),
        sa.Column("resource_type", sa.String(16), primary_key=True),
        sa.Column("resource_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(["project_id", "owner_id"], ["cw_projects.id", "cw_projects.owner_id"]),
        sa.CheckConstraint("resource_type IN ('conversation', 'document')", name="ck_cw_project_resource_type"))
    op.create_index("ix_cw_project_resources_owner_id", "cw_project_resources", ["owner_id"])

def downgrade():
    op.drop_table("cw_project_resources")
    op.drop_table("cw_projects")
