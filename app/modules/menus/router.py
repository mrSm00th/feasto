import asyncio
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.constants import (
    DINING_MENU_IMAGE_STORAGE_PREFIX,
    MENU_ITEM_IMAGE_STORAGE_PREFIX,
)
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
    RestaurantDiningMenuUploadResponse,
)
from app.modules.restaurants.models import (
    Restaurant,
    RestaurantImage,
    RestaurantImageType,
)
from app.modules.users.models import User, UserRole

router = APIRouter(
    prefix="/api/restaurants",
    tags=["menus"],
)

MAX_FILES_PER_REQUEST = settings.max_restaurant_images_per_request
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# MENU_ITEM_IMAGE_STORAGE_PREFIX = "menu-items"
# RESTAURANT_IMAGES_PREFIX = "restaurant_images"


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

    result = await db.execute(
        select(MenuItem.id).where(
            MenuItem.normalized_name == normalized_name,
            MenuItem.category_id == category_id,
        )
    )

    exisiting_menu_item = result.scalars().first()

    if exisiting_menu_item:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu Item already exists for this category",
        )

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


@router.post(
    "dining-menu/{restaurant_id}/images",
    response_model=RestaurantDiningMenuUploadResponse,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["files"],
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "maxItems": MAX_FILES_PER_REQUEST,
                                "description": f"Up to {MAX_FILES_PER_REQUEST} JPEG / PNG / WEBP files.",
                            }
                        },
                    }
                }
            },
            "required": True,
        }
    },
)
async def upload_restaurant_dining_menu_images(
    restaurant_id: uuid.UUID,
    files: Annotated[
        List[UploadFile], File(description="Restaurant images (JPEG/PNG/WEBP)")
    ],
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):

    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found."
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided."
        )

    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_FILES_PER_REQUEST} files per request.",
        )

    invalid = [f.filename for f in files if f.content_type not in ALLOWED_MIME_TYPES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type(s): {', '.join(invalid)}. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # Check per-restaurant image cap
    existing_count: int = (
        await db.scalar(
            select(func.count(RestaurantImage.id)).where(
                RestaurantImage.restaurant_id == restaurant_id,
                RestaurantImage.image_type == RestaurantImageType.DINING_MENU,
            )
        )
        or 0
    )

    # Used when Restraunts has storage limits - for dev applying storage limits
    remaining_slots = settings.max_dining_menu_images_per_restaurant - existing_count
    if remaining_slots <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Restaurant already has the maximum of "
            f"{settings.max_dining_menu_images_per_restaurant} images.",
        )
    if len(files) > remaining_slots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {remaining_slots} image slot(s) remaining "
            f"(max {settings.max_dining_menu_images_per_restaurant} total).",
        )

    # Validate all files before uploading any of them so we never
    # upload partial batches due to a bad file in the middle.
    processed: list[tuple[bytes, str]] = []  # (jpeg_bytes, storage_key)

    for file in files:
        raw = await file.read()
        try:
            # process_image -> (jpeg_bytes, filename)
            jpeg_bytes, filename = await run_in_threadpool(process_image, raw)
        except ImageProcessingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{file.filename}: {exc}",
            ) from exc

        key = _image_key(restaurant_id, filename, DINING_MENU_IMAGE_STORAGE_PREFIX)
        processed.append((jpeg_bytes, key))

    uploaded_keys: list[str] = []
    try:
        upload_tasks = [storage.upload(data, key) for data, key in processed]
        await asyncio.gather(*upload_tasks)
        uploaded_keys = [key for _, key in processed]

    except Exception as exc:

        await _cleanup_keys(storage, uploaded_keys)
        # logger.exception("Storage upload failed for restaurant %s", restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed. Please try again.",
        ) from exc

    db_images = [
        RestaurantImage(
            restaurant_id=restaurant_id,
            image_url=key,
            image_type=RestaurantImageType.DINING_MENU,
        )
        for key in uploaded_keys
    ]

    db.add_all(db_images)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await _cleanup_keys(storage, uploaded_keys)
        # logger.exception("DB commit failed for restaurant %s images", restaurant_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save image records. Uploaded files have been removed.",
        ) from exc

    for img in db_images:
        await db.refresh(img)

    return {
        "uploaded": len(db_images),
        "images": [
            {
                "id": img.id,
                "image_path": storage.public_url(img.image_url),
            }
            for img in db_images
        ],
    }
