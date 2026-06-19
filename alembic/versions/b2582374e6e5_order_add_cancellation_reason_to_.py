"""(order) add cancellation reason to support auto cancellation of rider in case of 'no rider available'

Revision ID: b2582374e6e5
Revises: 6b2380a91a1e
Create Date: 2026-06-19 18:55:54.394220

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2582374e6e5"
down_revision: Union[str, Sequence[str], None] = "6b2380a91a1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE cancellationreason ADD VALUE IF NOT EXISTS 'NO_RIDER_AVAILABLE'"
    )


def downgrade() -> None:
    pass
