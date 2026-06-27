"""rename auth_tokens to otp_verifications

Revision ID: 3a34b10df877
Revises: e962050ce23a
Create Date: 2026-06-27 11:05:48.744932

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "3a34b10df877"
down_revision: Union[str, Sequence[str], None] = "e962050ce23a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'otppurpose') THEN
                CREATE TYPE otppurpose AS ENUM ('EMAIL_VERIFICATION', 'PASSWORD_RESET');
            END IF;
        END$$;
    """)

    op.create_table(
        "otp_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("otp_hash", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),  # Text first, cast after
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # cast text column to the enum type
    op.execute("""
        ALTER TABLE otp_verifications
        ALTER COLUMN purpose TYPE otppurpose
        USING purpose::otppurpose
    """)

    op.create_index("ix_otp_user_purpose", "otp_verifications", ["user_id", "purpose"])
    op.create_index("ix_otp_verifications_user_id", "otp_verifications", ["user_id"])

    op.drop_index("ix_auth_tokens_user_purpose", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.execute("DROP TYPE IF EXISTS authtokenpurpose")


def downgrade() -> None:
    # recreate auth_tokens
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
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum(
                "EMAIL_VERIFICATION",
                "PASSWORD_RESET",
                name="authtokenpurpose",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_auth_tokens_user_purpose", "auth_tokens", ["user_id", "purpose"]
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])

    # drop otp_verifications
    op.drop_index("ix_otp_user_purpose", table_name="otp_verifications")
    op.drop_index("ix_otp_verifications_user_id", table_name="otp_verifications")
    op.drop_table("otp_verifications")
    op.execute("DROP TYPE IF EXISTS otppurpose")
