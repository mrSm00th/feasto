"""(user) added RIDER enum

Revision ID: 8887cf1f934c
Revises: b2582374e6e5
Create Date: 2026-06-19 23:59:37.579138

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8887cf1f934c"
down_revision: Union[str, Sequence[str], None] = "b2582374e6e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'RIDER';")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # Downgrade intentionally left empty.
    pass
