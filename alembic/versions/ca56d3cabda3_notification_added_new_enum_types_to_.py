"""(notification) added new enum types to support order preparationa and order ready for pickup

Revision ID: ca56d3cabda3
Revises: ea4cf08db604
Create Date: 2026-06-17 12:25:18.015544

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ca56d3cabda3"
down_revision: Union[str, Sequence[str], None] = "ea4cf08db604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE to add new enum values —
    # this is different from creating a brand-new enum type (which
    # you did before with sa.Enum(...).create()). Here the type
    # already exists, you're just adding values to it.
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_PREPARING'")
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_READY_FOR_PICKUP'"
    )


def downgrade() -> None:
    # PostgreSQL does NOT support removing individual enum values directly.
    # The only clean way to "remove" a value is to recreate the type:
    # 1. rename old type
    # 2. create new type without the value
    # 3. alter the column to use the new type
    # 4. drop the old type
    # This is involved enough that most teams just leave added enum
    # values in place on downgrade (harmless — unused value sitting
    # in the type) rather than building the full recreate dance.
    pass
