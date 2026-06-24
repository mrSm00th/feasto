import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_delete, cache_delete_pattern
from app.core.cache_keys import (
    discovery_feed_pattern_for_restaurant_city,
    restaurant_detail_key,
)
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.restaurants.models import (
    AvailabilityStatus,
    CuisineType,
    Restaurant,
    RestaurantAvailability,
    RestaurantClosure,
    RestaurantCuisineMapping,
    RestaurantStatus,
)


async def get_restaurant_with_owner(
    restaurant_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Restaurant)
        .options(selectinload(Restaurant.owner))
        .where(Restaurant.id == restaurant_id)
    )

    restaurant = result.scalar_one_or_none()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    return restaurant


async def get_restaurant_owned_by(
    restaurant_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user_id,
        )
    )

    restaurant = result.scalar_one_or_none()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="restaurant not found",
        )

    return restaurant


async def find_restaurants_near(
    lat: float,
    lon: float,
    db: AsyncSession,
    radius_km: float = 10.0,
) -> list[tuple[Restaurant, float]]:
    point = cast(ST_SetSRID(ST_MakePoint(lon, lat), 4326), Geography)
    distance_expr = ST_Distance(Restaurant.location, point)

    result = await db.execute(
        select(Restaurant, distance_expr.label("distance_m"))
        .where(
            Restaurant.status == RestaurantStatus.ACTIVE,
            Restaurant.location.isnot(None),
            ST_DWithin(Restaurant.location, point, radius_km * 1000),
        )
        .order_by(distance_expr.asc())
    )
    return [(r, d / 1000.0) for r, d in result.all()]


async def discover_restaurants_service(
    db: AsyncSession,
    lat: float | None = None,
    lon: float | None = None,
    city: str | None = None,
    cuisine_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[Restaurant], str | None, bool]:

    now = datetime.now(UTC)
    current_time = now.astimezone(UTC).timetz()
    today_dow = now.isoweekday() - 1

    active_closure_subquery = (
        select(RestaurantClosure.restaurant_id)
        .where(
            RestaurantClosure.starts_at <= now,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
        .scalar_subquery()
    )

    base_filters = [
        Restaurant.status == RestaurantStatus.ACTIVE,
        Restaurant.is_manually_paused.is_(False),
        Restaurant.id.not_in(active_closure_subquery),
        RestaurantAvailability.restaurant_id == Restaurant.id,
        RestaurantAvailability.day_of_week == today_dow,
        RestaurantAvailability.status == AvailabilityStatus.OPEN,
        RestaurantAvailability.opening_time <= current_time,
        RestaurantAvailability.closing_time > current_time,
    ]

    if cuisine_id:
        base_filters.append(Restaurant.cuisines.any(CuisineType.id == cuisine_id))

    if lat is not None and lon is not None:
        point = cast(ST_SetSRID(ST_MakePoint(lon, lat), 4326), Geography)
        distance_expr = ST_Distance(Restaurant.location, point)

        query = (
            select(Restaurant, distance_expr.label("distance_m"))
            .join(
                RestaurantAvailability,
                RestaurantAvailability.restaurant_id == Restaurant.id,
            )
            .options(
                selectinload(Restaurant.primary_image),
                selectinload(Restaurant.restaurant_cuisines).selectinload(
                    RestaurantCuisineMapping.cuisine
                ),
            )
            .where(*base_filters, Restaurant.location.isnot(None))
        )

        if cursor:
            cursor_distance_str, cursor_id = decode_cursor(cursor)
            cursor_distance = float(cursor_distance_str)
            query = query.where(
                (distance_expr > cursor_distance)
                | ((distance_expr == cursor_distance) & (Restaurant.id > cursor_id))
            )

        query = query.order_by(distance_expr.asc(), Restaurant.id.asc()).limit(
            limit + 1
        )

        result = await db.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        for restaurant, distance_m in rows:
            restaurant._distance_km = distance_m / 1000.0

        restaurants = [r for r, _ in rows]
        next_cursor = (
            encode_cursor(rows[-1][1], rows[-1][0].id) if has_more and rows else None
        )

        return restaurants, next_cursor, has_more

    else:
        if not city:
            raise HTTPException(
                status_code=400, detail="Provide either lat/lon or city"
            )

        normalized = city.strip().lower()
        base_filters.append(Restaurant.normalized_city == normalized)

        query = (
            select(Restaurant)
            .join(
                RestaurantAvailability,
                RestaurantAvailability.restaurant_id == Restaurant.id,
            )
            .options(
                selectinload(Restaurant.primary_image),
                selectinload(Restaurant.restaurant_cuisines).selectinload(
                    RestaurantCuisineMapping.cuisine
                ),
            )
            .where(*base_filters)
        )

        if cursor:
            cursor_rating_str, cursor_id = decode_cursor(cursor)
            cursor_rating = Decimal(cursor_rating_str)
            query = query.where(
                (Restaurant.avg_rating < cursor_rating)
                | (
                    (Restaurant.avg_rating == cursor_rating)
                    & (Restaurant.id > cursor_id)
                )
            )

        query = query.order_by(Restaurant.avg_rating.desc(), Restaurant.id.asc()).limit(
            limit + 1
        )

        result = await db.execute(query)
        restaurants = result.scalars().all()

        has_more = len(restaurants) > limit
        restaurants = restaurants[:limit]

        next_cursor = (
            encode_cursor(restaurants[-1].avg_rating, restaurants[-1].id)
            if has_more and restaurants
            else None
        )

        return restaurants, next_cursor, has_more


async def invalidate_restaurant_caches(restaurant) -> None:

    await cache_delete(restaurant_detail_key(restaurant.id))
    if restaurant.city:
        await cache_delete_pattern(
            discovery_feed_pattern_for_restaurant_city(restaurant.city)
        )
