import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.restaurants.models import Restaurant


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
