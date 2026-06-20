"""(notification) renamed the enum order_pickuped to order_picked_up

Revision ID: ceca786dfe6e
Revises: 64270c67c5d2
Create Date: 2026-06-20 12:27:07.930496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ceca786dfe6e'
down_revision: Union[str, Sequence[str], None] = '64270c67c5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE notificationtype
        RENAME VALUE 'ORDER_PICKUPED'
        TO 'ORDER_PICKED_UP';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TYPE notificationtype
        RENAME VALUE 'ORDER_PICKED_UP'
        TO 'ORDER_PICKUPED';
        """
    )