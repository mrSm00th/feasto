"""fix enum bug in rider application

Revision ID: 09261014cf0d
Revises: 1338daf571cf
Create Date: 2026-06-18 17:11:29.192773

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "09261014cf0d"
down_revision: Union[str, Sequence[str], None] = "1338daf571cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Drop index that references the enum
    op.execute("""
        DROP INDEX IF EXISTS uq_rider_applications_active_per_user;
    """)

    # Drop default
    op.execute("""
        ALTER TABLE rider_applications
        ALTER COLUMN status DROP DEFAULT;
    """)

    # Remove column completely (table is empty)
    op.execute("""
        ALTER TABLE rider_applications
        DROP COLUMN status;
    """)

    # Remove old enum
    op.execute("""
        DROP TYPE IF EXISTS riderapplicationstatus;
    """)

    # Recreate enum
    op.execute("""
        CREATE TYPE riderapplicationstatus AS ENUM (
            'CITY_ADDED',
            'IDENTITY_PROOF_ADDED',
            'PROFILE_IMAGE_ADDED',
            'VEHICLE_DETAILS_ADDED',
            'PENDING_REVIEW',
            'APPROVED',
            'REJECTED'
        );
    """)

    # Recreate column
    op.execute("""
        ALTER TABLE rider_applications
        ADD COLUMN status riderapplicationstatus
        NOT NULL
        DEFAULT 'CITY_ADDED';
    """)

    # Recreate partial unique index
    op.execute("""
        CREATE UNIQUE INDEX uq_rider_applications_active_per_user
        ON rider_applications (applicant_id)
        WHERE status NOT IN ('APPROVED', 'REJECTED');
    """)


def downgrade():
    pass
