import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.restaurants.models import Restaurant, RestaurantImage, RestaurantStatus
from app.modules.restaurants.schemas import (
    RestaurantCreate,
    RestaurantCreateResponse,
    RestaurantDocumentsUpload,
    RestaurantDocumentsUploadResponse,
    RestaurantImageUploadResponse,
)
from app.modules.restaurants.utils import (
    delete_image,
    generate_unique_slug,
    normalize,
    process_image,
    upload_image,
)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error updating restaurant documents.",
        )

    await db.refresh(restaurant)

    return restaurant


MAX_FILES = 5
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/{restaurant_id}/images", response_model=RestaurantImageUploadResponse)
async def upload_restaurant_images(
    restaurant_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    current_user=Depends(require_roles(UserRole.RESTAURANT_OWNER)),
    db=Depends(get_db),
):

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    restaurant = result.scalars().first()

    if not restaurant:
        raise HTTPException(404, "Restaurant not found or not owned by user")

    if not files:
        raise HTTPException(400, "No files uploaded")

    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Max {MAX_FILES} files allowed")

    count_result = await db.execute(
        select(func.count()).where(RestaurantImage.restaurant_id == restaurant_id)
    )
    existing_count = count_result.scalar()

    if existing_count + len(files) > settings.max_images_per_restaurant:
        raise HTTPException(
            400,
            f"Max {settings.max_images_per_restaurant} images allowed per restaurant",
        )

    processed_images = []
    uploaded_keys = []

    try:

        for file in files:
            if file.content_type not in ALLOWED_TYPES:
                raise HTTPException(400, f"{file.filename} has invalid type")

            content = await file.read()

            processed_bytes, filename = await run_in_threadpool(process_image, content)

            await upload_image(processed_bytes, filename)

            processed_images.append(filename)
            uploaded_keys.append(filename)

        db_images = [
            RestaurantImage(
                restaurant_id=restaurant_id,
                image_url=filename,
            )
            for filename in processed_images
        ]

        db.add_all(db_images)
        await db.commit()

        return {
            "uploaded": processed_images,
            "count": len(processed_images),
        }

    except Exception as e:

        for filename in uploaded_keys:
            await delete_image(filename)

        await db.rollback()
        raise HTTPException(500, "Image upload failed") from e
