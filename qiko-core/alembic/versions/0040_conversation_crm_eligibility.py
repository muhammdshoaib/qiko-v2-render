"""Store immutable CRM eligibility provenance on conversations."""
from alembic import op
import sqlalchemy as sa

revision = "0040_conversation_crm_eligible"
down_revision = "0039_audit_append_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column(
            "crm_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.alter_column(
            "user_id", existing_type=sa.String(64), type_=sa.String(320),
            existing_nullable=False)

    conversations = sa.table(
        "conversations",
        sa.column("user_id", sa.String(320)),
        sa.column("crm_eligible", sa.Boolean()),
    )
    op.execute(
        conversations.update()
        .where(conversations.c.user_id != "public")
        .values(crm_eligible=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.alter_column(
            "user_id", existing_type=sa.String(320), type_=sa.String(64),
            existing_nullable=False)
        batch_op.drop_column("crm_eligible")
