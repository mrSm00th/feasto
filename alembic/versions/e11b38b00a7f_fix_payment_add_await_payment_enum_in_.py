"""fix(payment) add await payment enum in the payment model

Revision ID: e11b38b00a7f
Revises: ab3abbc876be
Create Date: 2026-06-13 18:30:02.086573

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e11b38b00a7f"
down_revision: Union[str, Sequence[str], None] = "ab3abbc876be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# in your new migration file
def upgrade() -> None:
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'AWAITING_PAYMENT'")


def downgrade() -> None:
    # Postgres doesn't support removing enum values natively
    # you'd need to recreate the type entirely — usually just leave this as pass
    pass
