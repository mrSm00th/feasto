"""(Restaurant) renamed the is_submitted & submitted_at to is_activaed and activated_at &
    (RestaurantAvailability) updated the opening and closing time to use timezone=True

Revision ID: 1c0c32f296d6
Revises: a9de46d8300a
Create Date: 2026-06-10 00:01:57.934339

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c0c32f296d6"
down_revision: Union[str, Sequence[str], None] = "a9de46d8300a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "restaurant_availability",
        "opening_time",
        existing_type=postgresql.TIME(),
        type_=sa.Time(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "restaurant_availability",
        "closing_time",
        existing_type=postgresql.TIME(),
        type_=sa.Time(timezone=True),
        existing_nullable=True,
    )

    # Step 1: Add nullable with a server_default to fill existing rows
    op.add_column(
        "restaurants",
        sa.Column(
            "is_activated",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "restaurants",
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Step 2: Drop the server_default (so the model stays in control),
    #         then enforce NOT NULL
    op.alter_column(
        "restaurants",
        "is_activated",
        existing_type=sa.Boolean(),
        server_default=None,
        nullable=False,
    )

    op.drop_column("restaurants", "is_submitted")
    op.drop_column("restaurants", "submitted_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "restaurants",
        sa.Column(
            "submitted_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
    )
    # Same pattern in reverse for is_submitted
    op.add_column(
        "restaurants",
        sa.Column(
            "is_submitted",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        "restaurants",
        "is_submitted",
        existing_type=sa.Boolean(),
        server_default=None,
        nullable=False,
    )

    op.drop_column("restaurants", "activated_at")
    op.drop_column("restaurants", "is_activated")

    op.alter_column(
        "restaurant_availability",
        "closing_time",
        existing_type=sa.Time(timezone=True),
        type_=postgresql.TIME(),
        existing_nullable=True,
    )
    op.alter_column(
        "restaurant_availability",
        "opening_time",
        existing_type=sa.Time(timezone=True),
        type_=postgresql.TIME(),
        existing_nullable=True,
    )
