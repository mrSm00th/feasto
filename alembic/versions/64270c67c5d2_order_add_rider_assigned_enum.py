"""(order) add Rider_Assigned enum

Revision ID: 64270c67c5d2
Revises: d854c1e796c4
Create Date: 2026-06-20 00:59:18.483747

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64270c67c5d2"
down_revision: Union[str, Sequence[str], None] = "d854c1e796c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TYPE orderstatus
        ADD VALUE IF NOT EXISTS 'RIDER_ASSIGNED';
        """)


def downgrade() -> None:
    # PostgreSQL does not support dropping enum values directly.
    # Intentionally left empty.
    pass
