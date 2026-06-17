"""(notification) added enum types to support restaurant order updates through websocket

Revision ID: ea4cf08db604
Revises: e11b38b00a7f
Create Date: 2026-06-15 11:39:25.280140

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ea4cf08db604"
down_revision: Union[str, Sequence[str], None] = "e11b38b00a7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_PLACED';")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_CONFIRMED';")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_REJECTED';")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'ORDER_CANCELLED';")


def downgrade() -> None:
    raise NotImplementedError("PostgreSQL enums do not support dropping values.")
