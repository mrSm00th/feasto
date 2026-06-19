import math
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.riders.models import Rider, RiderProfileStatus

# Constants

EARTH_RADIUS_KM = 6371.0
DEFAULT_SEARCH_RADIUS_KM = 5.0  # initial search radius
MAX_SEARCH_RADIUS_KM = 15.0  # expand the search if no riders found nearby
CANDIDATE_POOL_SIZE = 5  # notify top N closest riders simultaneously
RIDER_ACCEPTANCE_TIMEOUT_SECONDS = 30  # rider has this long to accept before auto skip


# creating a box around the restaurant to filter out riders
def _bounding_box(
    lat: float, lon: float, radius_km: float
) -> tuple[float, float, float, float]:
    """
    Return (min_lat, max_lat, min_lon, max_lon) for a square bounding box
    around (lat, lon) of size radius_km.

    Over estimates the rider around the corners of actual circle

    1 degree latitude ≈ 111km everywhere.
    1 degree longitude ≈ 111km * cos(lat) — using this formula as long. shrinks around poles.
    """
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (
        lat - lat_delta,
        lat + lat_delta,
        lon - lon_delta,
        lon + lon_delta,
    )


# Haversine distance - for exact filtering after the bounding box approximation


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate the great-circle distance in kilometres between two points
    on Earth using the Haversine formula. This is more accurate than
    Euclidean distance for geographic coordinates, especially over longer
    distances where the Earth's curvature matters.

    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# Core matching logic


async def find_nearby_riders(
    restaurant_lat: float,
    restaurant_lon: float,
    db: AsyncSession,
    radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
) -> list[tuple[Rider, float]]:
    """
    Find available riders within radius_km of the pickup point.

    Returns a list of (rider, distance_km) tuples sorted by:
        1. Distance ascending (closest first — primary sort)
        2. avg_rating descending (higher rated first — tiebreaker)

    Two-level approach:
        Level 1: Using Bounding Box- a db level approximate filtering
                that over estimates the riders within the specified range
                but filters most of the riders

        Level 2: Python-level Haversine calculation on the small
                 candidate set returned by level 1.

    Stale-location guard: riders whose last_location_update is older
    than 5 minutes are treated as effectively offline regardless of
    their is_online flag.
    This handles app crashes without clean logout.
    """
    staleness_cutoff = datetime.now(UTC) - timedelta(minutes=5)
    min_lat, max_lat, min_lon, max_lon = _bounding_box(
        restaurant_lat, restaurant_lon, radius_km
    )

    # level-1: performs the bound box
    result = await db.execute(
        select(Rider).where(
            Rider.is_online.is_(True),
            Rider.is_available.is_(True),
            Rider.status == RiderProfileStatus.ACTIVE,
            Rider.current_latitude.isnot(None),
            Rider.current_longitude.isnot(None),
            Rider.last_location_update >= staleness_cutoff,
            Rider.current_latitude.between(min_lat, max_lat),
            Rider.current_longitude.between(min_lon, max_lon),
        )
    )
    candidates = result.scalars().all()

    # Level-2: precise Haversine filter
    riders_with_distance: list[tuple[Rider, float]] = []
    for rider in candidates:
        distance = haversine_km(
            restaurant_lat,
            restaurant_lon,
            float(rider.current_latitude),
            float(rider.current_longitude),
        )
        if distance <= radius_km:
            riders_with_distance.append((rider, distance))

    # Sort: closest first, higher rated as tiebreaker
    riders_with_distance.sort(key=lambda t: (t[1], -float(t[0].avg_rating)))
    return riders_with_distance
