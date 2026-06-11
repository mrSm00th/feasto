"""(Restaurant) renamed is_manually_closed -> to -> is_manually_paused

Revision ID: a2b60ddba5dd
Revises: 8ccc04a91d16
Create Date: 2026-06-11 00:13:58.668913

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b60ddba5dd"
down_revision: Union[str, Sequence[str], None] = "8ccc04a91d16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        "restaurants",
        "is_manually_closed",
        new_column_name="is_manually_paused",
    )


def downgrade():
    op.alter_column(
        "restaurants",
        "is_manually_paused",
        new_column_name="is_manually_closed",
    )
