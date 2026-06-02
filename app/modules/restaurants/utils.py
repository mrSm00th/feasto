from __future__ import annotations

import re
import unicodedata
import uuid
from math import asin, cos, radians, sin, sqrt

from fastapi import HTTPException, status
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.restaurants.models import Restaurant


def normalize(text: str) -> str:
    return text.strip().lower()


async def generate_unique_slug(db: AsyncSession, name: str, city: str) -> str:
    """
    Produce a URL-safe slug in the form  {name}-{city}  or
    {name}-{city}-{n}  (n ≥ 2) if a collision exists.

    The LIKE pre-filter keeps the query fast; the regex post-filter
    ensures we only count exact variants, not unrelated restaurants
    whose slug happens to share the same prefix.
    """
    base_slug = slugify(f"{name} {city}")

    # Only fetch slugs that are this base or could be numbered variants of it
    candidate_pattern = re.compile(rf"^{re.escape(base_slug)}(-\d+)?$")

    result = await db.execute(
        select(Restaurant.slug).where(Restaurant.slug.like(f"{base_slug}%"))
    )
    existing = {row[0] for row in result.all() if candidate_pattern.match(row[0])}

    if base_slug not in existing:
        return base_slug

    # Start at 2 so the series reads:
    #   mcdonalds-mumbai  →  mcdonalds-mumbai-2  →  mcdonalds-mumbai-3
    counter = 2
    while f"{base_slug}-{counter}" in existing:
        counter += 1

    return f"{base_slug}-{counter}"


# Geo distance  (Haversine)


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the distance in metres between two (lat, lon) points."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6_371_000  # Earth radius in metres


def _get_upsert_fn():
    """
    Return the dialect-specific `insert` function.
    Centralised here so every route stays dialect-agnostic.
    Switch from SQLite to PostgreSQL by changing DATABASE_URL — no route changes.
    """
    db_url: str = settings.database_url
    if db_url.startswith("postgresql"):
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


async def _get_owned_restaurant(
    restaurant_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> Restaurant:
    """
    Fetch a restaurant and verify ownership in one query.
    Raises 404 for both "not found" and "not owned" — avoids leaking
    the existence of restaurants owned by others.
    """
    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == owner_id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found.",
        )
    return restaurant


def _build_availability_rows(
    restaurant_id: uuid.UUID,
    shifts: list,
) -> list[dict]:
    """Convert validated schema entries into dicts for bulk upsert."""
    return [
        {
            "id": uuid.uuid4(),
            "restaurant_id": restaurant_id,
            "day_of_week": entry.day_of_week,
            "status": entry.status,
            "opening_time": entry.opening_time,
            "closing_time": entry.closing_time,
            "shift_index": entry.shift_index,
        }
        for entry in shifts
    ]


def normalize_cuisine_name(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("Cuisine name cannot be empty")

    # normalize the cuisine name
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    name = name.lower()

    # Standardizing the  connectors
    name = re.sub(r"\s*(&|\+|/)\s*", " and ", name)

    # Replacing the separators
    name = re.sub(r"[-_]+", " ", name)

    # Remove special chars
    name = re.sub(r"[^a-z0-9 ]+", "", name)

    # Collapse spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name.title()


def slugify(value: str) -> str:

    # Normalize unicode characters (é -> e)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    value = value.lower()

    # Replacing all  non-alphanumeric chars with hyphen
    value = re.sub(r"[^a-z0-9]+", "-", value)

    # Removing any  leading/trailing hyphens
    value = value.strip("-")

    return value
