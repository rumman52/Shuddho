"""agent workflow outbox

Revision: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cw_agent_outbox",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cw_agent_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_cw_agent_outbox_delivered"), "cw_agent_outbox", ["delivered"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_cw_agent_outbox_delivered"), table_name="cw_agent_outbox")
    op.drop_table("cw_agent_outbox")
