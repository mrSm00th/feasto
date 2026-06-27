"""(users) DB-level case-insensitive unique index on email

Revision ID: d996e9ac1136
Revises: 3a34b10df877
Create Date: 2026-06-27 22:46:59.206478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd996e9ac1136'
down_revision: Union[str, Sequence[str], None] = '3a34b10df877'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_users_email_lower
        ON users (lower(email))
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
    # ### end Alembic commands ###
