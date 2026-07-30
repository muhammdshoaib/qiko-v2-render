"""Expand TOTP secret storage for encrypted values."""
from alembic import op
import sqlalchemy as sa

revision = "0026_encrypt_totp_secrets"
down_revision = "0025_agent_enabled_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("totp_secret", existing_type=sa.String(length=64), type_=sa.String(length=512), existing_nullable=True)
    from app.core.crypto import encrypt

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL")).fetchall()
    for user_id, secret in rows:
        if not secret.startswith("enc:"):
            connection.execute(sa.text("UPDATE users SET totp_secret = :secret WHERE id = :user_id"),
                               {"secret": f"enc:{encrypt(secret)}", "user_id": user_id})


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("totp_secret", existing_type=sa.String(length=512), type_=sa.String(length=64), existing_nullable=True)
