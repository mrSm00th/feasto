"""(notification) fix the notification enums tosupport the order lifecycle

Revision ID: 652f861236da
Revises: ceca786dfe6e
Create Date: 2026-06-20 13:43:08.949746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '652f861236da'
down_revision: Union[str, Sequence[str], None] = 'ceca786dfe6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'NEW_DELIVERY_AVAILABLE'")

def downgrade() -> None:
    pass
