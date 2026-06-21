"""(addresses) added location column for postgis

Revision ID: df35f2407542
Revises: 5ba19aed112e
Create Date: 2026-06-21 21:21:57.746312

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "df35f2407542"
down_revision: Union[str, Sequence[str], None] = "5ba19aed112e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE addresses ADD COLUMN location geography(Point, 4326)")
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_address_location()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
                NEW.location := ST_SetSRID(
                    ST_MakePoint(NEW.longitude::float, NEW.latitude::float), 4326
                )::geography;
            ELSE
                NEW.location := NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_sync_address_location
        BEFORE INSERT OR UPDATE OF latitude, longitude ON addresses
        FOR EACH ROW EXECUTE FUNCTION sync_address_location();
    """)
    op.execute(
        "CREATE INDEX idx_addresses_location_gist ON addresses USING GIST (location)"
    )
    op.execute("UPDATE addresses SET latitude = latitude WHERE latitude IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_address_location ON addresses")
    op.execute("DROP FUNCTION IF EXISTS sync_address_location")
    op.execute("DROP INDEX IF EXISTS idx_addresses_location_gist")
    op.execute("ALTER TABLE addresses DROP COLUMN IF EXISTS location")
