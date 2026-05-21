import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.restaurants.models import Restaurant, RestaurantStatus
from app.modules.restaurants.schemas import (
    RestaurantCreate,
    RestaurantCreateResponse,
    RestaurantDocumentsUpload,
    RestaurantDocumentsUploadResponse,
)
from app.modules.restaurants.utils import generate_unique_slug, normalize
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


@router.post(
    "/",
    response_model=RestaurantCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_restaurant_draft(
    data: RestaurantCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    normalized_name = normalize(data.name)
    normalized_address_line_1 = normalize(data.address_line_1)
    normalized_city = normalize(data.city)

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.owner_id == current_user.id,
            Restaurant.normalized_name == normalized_name,
            Restaurant.normalized_address_line_1 == normalized_address_line_1,
            Restaurant.normalized_city == normalized_city,
        )
    )

    existing_restaurant = result.scalars().first()

    if existing_restaurant:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A restaurant with the same name and address already exists for this owner.",
        )

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.normalized_name == normalized_name,
            Restaurant.normalized_city == normalized_city,
        )
    )

    slug = await generate_unique_slug(db, data.name)

    new_restaurant = Restaurant(
        owner_id=current_user.id,
        name=data.name,
        normalized_name=normalized_name,
        phone_number=data.phone_number,
        address_line_1=data.address_line_1,
        normalized_address_line_1=normalized_address_line_1,
        address_line_2=data.address_line_2,
        city=data.city,
        normalized_city=normalized_city,
        state=data.state,
        postal_code=data.postal_code,
        country=data.country,
        slug=slug,
        status=RestaurantStatus.DRAFT,
    )

    db.add(new_restaurant)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(400, detail=str(error))
    await db.refresh(new_restaurant)

    return new_restaurant


@router.patch(
    "/{restaurant_id}/documents",
    response_model=RestaurantDocumentsUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_restaurant_documents(
    restaurant_id: uuid.UUID,
    data: RestaurantDocumentsUpload,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    restaurant = result.scalars().first()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    restaurant.fssai_license_number = data.fssai_license_number
    restaurant.gst_number = data.gst_number
    restaurant.status = RestaurantStatus.DOCUMENTS_ADDED

    db.add(restaurant)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "Error updating restaurant documents.")

    await db.refresh(restaurant)

    return restaurant
