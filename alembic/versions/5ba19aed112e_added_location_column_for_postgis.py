"""added location column for postgis

Revision ID: 5ba19aed112e
Revises: 3ea16726381f
Create Date: 2026-06-21 21:01:34.902220

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ba19aed112e"
down_revision: Union[str, Sequence[str], None] = "3ea16726381f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE riders ADD COLUMN location geography(Point, 4326)")
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_rider_location()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.current_latitude IS NOT NULL AND NEW.current_longitude IS NOT NULL THEN
                NEW.location := ST_SetSRID(
                    ST_MakePoint(NEW.current_longitude::float, NEW.current_latitude::float),
                    4326
                )::geography;
            ELSE
                NEW.location := NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_sync_rider_location
        BEFORE INSERT OR UPDATE OF current_latitude, current_longitude ON riders
        FOR EACH ROW EXECUTE FUNCTION sync_rider_location();
    """)
    op.execute("CREATE INDEX idx_riders_location_gist ON riders USING GIST (location)")

    # Same pattern for restaurants
    op.execute("ALTER TABLE restaurants ADD COLUMN location geography(Point, 4326)")
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_restaurant_location()
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
        CREATE TRIGGER trg_sync_restaurant_location
        BEFORE INSERT OR UPDATE OF latitude, longitude ON restaurants
        FOR EACH ROW EXECUTE FUNCTION sync_restaurant_location();
    """)
    op.execute(
        "CREATE INDEX idx_restaurants_location_gist ON restaurants USING GIST (location)"
    )

    # Backfill existing rows — trigger only fires on INSERT/UPDATE going
    # forward, so existing rows need a one-time sync
    op.execute("""
        UPDATE riders SET current_latitude = current_latitude
        WHERE current_latitude IS NOT NULL
    """)
    op.execute("""
        UPDATE restaurants SET latitude = latitude
        WHERE latitude IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_restaurant_location ON restaurants")
    op.execute("DROP FUNCTION IF EXISTS sync_restaurant_location")
    op.execute("DROP INDEX IF EXISTS idx_restaurants_location_gist")
    op.execute("ALTER TABLE restaurants DROP COLUMN IF EXISTS location")

    op.execute("DROP TRIGGER IF EXISTS trg_sync_rider_location ON riders")
    op.execute("DROP FUNCTION IF EXISTS sync_rider_location")
    op.execute("DROP INDEX IF EXISTS idx_riders_location_gist")
    op.execute("ALTER TABLE riders DROP COLUMN IF EXISTS location")
