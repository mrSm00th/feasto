import uuid

from fastapi import HTTPException, status
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.restaurants.models import Restaurant, RestaurantStatus


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
