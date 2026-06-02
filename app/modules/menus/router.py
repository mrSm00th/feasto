import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import require_roles
from app.core.image_processing import ImageProcessingError, _image_key, process_image
from app.core.storage import StorageBackend, _cleanup_keys, get_storage
from app.core.text import normalize
from app.db.database import get_db
from app.modules.menus.models import MenuCategory, MenuItem
from app.modules.menus.schemas import (
    CreateMenuCategory,
    ItemImageResponse,
    MenuCategoryCreateResponse,
    MenuItemCreate,
    MenuItemResponse,
)
from app.modules.restaurants.models import Restaurant
from app.modules.users.models import User, UserRole

router = APIRouter(
    prefix="/api/restaurants",
    tags=["menus"],
)


ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

MENU_ITEM_IMAGE_STORAGE_PREFIX = "menu-items"


@router.post(
    "/{restaurant_id}/menu-categories", response_model=MenuCategoryCreateResponse
)
async def create_menu_category(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: CreateMenuCategory,
):

    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    restaurant = result.scalars().first()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    normalized_name = normalize(data.name)

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.normalized_name == normalized_name,
        )
    )

    existing_menu_category = result.scalar_one_or_none()

    if existing_menu_category:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu category already exists",
        )

    new_menu_category = MenuCategory(
        restaurant_id=restaurant_id,
        name=data.name,
        normalized_name=normalized_name,
        description=data.description if data.description else None,
        display_order=data.display_order,
    )

    db.add(new_menu_category)

    try:

        await db.commit()
        await db.refresh(new_menu_category)

    except IntegrityError as exc:

        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=" A category for this Display order number already exists for this restaurant ",
        ) from exc

    return new_menu_category


@router.post(
    "/categories/{category_id}/items",
    response_model=MenuItemResponse,
)
async def create_menu_item(
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuItemCreate,
):

    result = await db.execute(
        select(MenuCategory)
        .join(Restaurant)
        .where(MenuCategory.id == category_id, Restaurant.owner_id == current_user.id)
    )

    try:
        category = result.scalar_one()

    except NoResultFound:
        raise HTTPException(
            status_code=404,
            detail="Menu category not found",
        )

    # just for extra safety
    except MultipleResultsFound:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data integrity error: multiple categories found.",
        )

    normalized_name = normalize(data.name)

    new_item = MenuItem(
        restaurant_id=category.restaurant_id,
        category_id=category.id,
        name=data.name,
        normalized_name=normalized_name,
        description=data.description if data.description else None,
        price=data.price,
        discounted_price=data.discounted_price if data.discounted_price else None,
        veg_type=data.veg_type,
        is_available=data.is_available,
        preparation_time_minutes=data.preparation_time_minutes,
        calories=data.calories if data.calories else None,
    )

    db.add(new_item)

    try:

        await db.commit()
        await db.refresh(new_item)

    except IntegrityError as exc:

        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=" Menu Item already exists for this category ",
        ) from exc

    return new_item


@router.put(
    "/items/{item_id}/image",
    response_model=ItemImageResponse,
)
async def upload_image_for_menu_item(
    item_id: uuid.UUID,
    image: Annotated[UploadFile, File(description="Menu item image (JPEG/PNG/WEBP)")],
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    result = await db.execute(
        select(MenuItem)
        .join(Restaurant)
        .where(
            MenuItem.id == item_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this owner",
        )

    if image.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type: {image.content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )

    raw = await image.read()

    try:
        jpeg_bytes, filename = await run_in_threadpool(
            process_image,
            raw,
        )
    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    key = _image_key(item_id, filename, MENU_ITEM_IMAGE_STORAGE_PREFIX)

    try:
        await storage.upload(jpeg_bytes, key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed.",
        ) from exc

    old_key = item.image_url

    item.image_url = key

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()

        await _cleanup_keys(storage, [key])

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save image information.",
        ) from exc

    await db.refresh(item)

    if old_key:
        try:
            await storage.delete(old_key)
        except Exception:
            pass

    return ItemImageResponse(
        id=item.id,
        image_path=storage.public_url(item.image_url),
    )
