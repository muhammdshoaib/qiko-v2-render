"""Persist account name and canonical onboarding worker with pending signups."""
from alembic import op
import sqlalchemy as sa

revision = "0041_onboarding_worker"
down_revision = "0040_conversation_crm_eligible"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pending_signups") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("onboarding_worker", sa.JSON(), nullable=True))
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("audit_events") as batch_op:
            batch_op.alter_column(
                "id", existing_type=sa.BigInteger(), type_=sa.Integer(),
                existing_nullable=False, autoincrement=True)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("audit_events") as batch_op:
            batch_op.alter_column(
                "id", existing_type=sa.Integer(), type_=sa.BigInteger(),
                existing_nullable=False, autoincrement=True)
    with op.batch_alter_table("pending_signups") as batch_op:
        batch_op.drop_column("onboarding_worker")
        batch_op.drop_column("name")
