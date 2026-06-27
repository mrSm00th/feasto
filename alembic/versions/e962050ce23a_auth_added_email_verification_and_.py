"""(auth) added email verification and password reset flow

Revision ID: e962050ce23a
Revises: df35f2407542
Create Date: 2026-06-25 22:54:16.777525

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op

revision: str = "e962050ce23a"
down_revision: Union[str, Sequence[str], None] = "df35f2407542"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'authtokenpurpose') THEN
                CREATE TYPE authtokenpurpose AS ENUM ('EMAIL_VERIFICATION', 'PASSWORD_RESET');
            END IF;
        END$$;
    """)

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column(
            "purpose",
            sa.Text(),  # store as text, constrained by the enum at DB level below
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # apply the enum type to the column after table creation
    op.execute("""
        ALTER TABLE auth_tokens
        ALTER COLUMN purpose TYPE authtokenpurpose
        USING purpose::authtokenpurpose
    """)

    op.create_index(
        "ix_auth_tokens_user_purpose", "auth_tokens", ["user_id", "purpose"]
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_user_purpose", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.execute("DROP TYPE IF EXISTS authtokenpurpose")
