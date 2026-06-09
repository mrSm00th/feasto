import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from app.modules.menus.models import (
    MenuCategory,
    MenuCategoryStatus,
    MenuItem,
    MenuItemStatus,
)
from app.modules.menus.schemas import (
    ItemImageResponse,
    MenuCategoryArchiveResponse,
    MenuCategoryCreateRequest,
    MenuCategoryCreateResponse,
    MenuCategoryItemReorderRequest,
    MenuCategoryItemReorderResponse,
    MenuCategoryListResponse,
    MenuCategoryReorderRequest,
    MenuCategoryReorderResponse,
    MenuCategoryUnarchiveResponse,
    MenuCategoryUpdateRequest,
    MenuCategoryUpdateResponse,
    MenuItemAvailabilityRequest,
    MenuItemCreate,
    MenuItemCreateResponse,
    MenuItemPaginatedResponse,
    MenuItemUpdateRequest,
    MenuItemUpdateResponse,
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


@router.post(
    "/{restaurant_id}/menu-categories", response_model=MenuCategoryCreateResponse
)
async def create_menu_category(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuCategoryCreateRequest,
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
        if existing_menu_category.status == MenuCategoryStatus.ARCHIVED:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archived Category with same name found for this restaurant with ID: {existing_menu_category.id} ",
            )

        else:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Menu category already exists",
            )

    result = await db.execute(
        select(func.max(MenuCategory.sort_order)).where(
            MenuCategory.restaurant_id == restaurant_id
        )
    )

    max_sort_order = result.scalars().first()

    sort_order = (max_sort_order or 0) + 1

    new_menu_category = MenuCategory(
        restaurant_id=restaurant_id,
        name=data.name,
        normalized_name=normalized_name,
        description=data.description.strip() or None,
        sort_order=sort_order,
    )

    db.add(new_menu_category)

    try:

        await db.commit()
        await db.refresh(new_menu_category)

    except IntegrityError as exc:

        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=" A category for this sort order number already exists for this restaurant ",
        ) from exc

    return new_menu_category


@router.get("/{restaurant_id}/menu-categories", response_model=MenuCategoryListResponse)
async def get_all_menu_categories_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
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

    result = await db.execute(
        select(MenuCategory)
        .where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.status.in_(
                [MenuCategoryStatus.ACTIVE, MenuCategoryStatus.ARCHIVED],
            ),
        )
        .order_by(MenuCategory.sort_order.asc())
    )

    menu_categories = result.scalars().all()

    return MenuCategoryListResponse(
        menu_categories=menu_categories,
        total_categories=len(menu_categories),
        restaurant_id=restaurant_id,
    )


# =========================
# CREATE MENU ITEM
# =========================


@router.post(
    "/{restaurant_id}/menu-categories/{category_id}/items",
    response_model=MenuItemCreateResponse,
)
async def create_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.RESTAURANT_OWNER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuItemCreate,
):

    # =========================
    # VERIFY CATEGORY BELONGS TO
    # THE OWNER AND RESTAURANT
    # =========================
    result = await db.execute(
        select(MenuCategory)
        .join(Restaurant)
        .where(
            MenuCategory.id == category_id,
            MenuCategory.restaurant_id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    try:
        category = result.scalar_one()

    except NoResultFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found",
        )

    # just a Defensive check against data corruption
    except MultipleResultsFound:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data integrity error: multiple categories found.",
        )

    normalized_name = normalize(data.name)

    # =========================
    # CHECK DUPLICATE ITEM
    # WITHIN CATEGORY
    # =========================
    result = await db.execute(
        select(MenuItem.id).where(
            MenuItem.category_id == category_id,
            MenuItem.normalized_name == normalized_name,
        )
    )

    existing_menu_item = result.scalars().first()

    if existing_menu_item:

        if existing_menu_item.status == MenuItemStatus.ARCHIVED:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archived menu item with same name and category found for this restaurant with ID: {existing_menu_item.id} ",
            )

        else:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Menu category already exists",
            )

    result = await db.execute(
        select(func.max(MenuItem.sort_order)).where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.category_id == category_id,
        )
    )

    max_sort_order = result.scalars().first()

    sort_order = (max_sort_order or 0) + 1

    new_item = MenuItem(
        restaurant_id=category.restaurant_id,
        category_id=category.id,
        name=data.name,
        normalized_name=normalized_name,
        sort_order=sort_order,
        description=data.description,
        price=data.price,
        discounted_price=data.discounted_price,
        veg_type=data.veg_type,
        is_available=data.is_available,
        preparation_time_minutes=data.preparation_time_minutes,
        calories=data.calories,
    )

    db.add(new_item)

    try:
        await db.commit()
        await db.refresh(new_item)

    except IntegrityError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create menu item.",
            # detail=str(exc),
        ) from exc

    return new_item


# =========================
# UPLOAD MENU ITEM IMAGE
# =========================
@router.put(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}/image",
    response_model=ItemImageResponse,
)
async def upload_image_for_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    image: Annotated[UploadFile, File(description="Menu item image (JPEG/PNG/WEBP)")],
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):

    # =========================
    # VERIFY ITEM OWNERSHIP
    # AND URL CONSISTENCY
    # =========================
    result = await db.execute(
        select(MenuItem)
        .join(Restaurant)
        .where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found",
        )

    # =========================
    # VALIDATE MIME TYPE
    # =========================
    if image.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported file type: {image.content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )

    # =========================
    # READ IMAGE
    # =========================
    raw = await image.read()

    # =========================
    # PROCESS IMAGE
    # =========================
    try:
        jpeg_bytes, filename = await run_in_threadpool(
            process_image,
            raw,
        )

    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Failed to process image. Ensure it is a valid "
                "JPEG, PNG, or WEBP image and is not corrupted."
            ),
        ) from exc

    # =========================
    # GENERATE STORAGE KEY
    # =========================
    key = _image_key(
        item_id,
        filename,
        MENU_ITEM_IMAGE_STORAGE_PREFIX,
    )

    # =========================
    # UPLOAD TO STORAGE
    # =========================
    try:
        await storage.upload(jpeg_bytes, key)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed.",
        ) from exc

    old_key = item.image_url

    # =========================
    # UPDATE DATABASE
    # =========================
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

    # =========================
    # DELETE OLD IMAGE
    # AFTER SUCCESSFUL COMMIT
    # =========================
    if old_key:
        try:
            await storage.delete(old_key)
        except Exception:
            pass

    # =========================
    # RETURN RESPONSE
    # =========================
    return ItemImageResponse(
        id=item.id,
        image_path=storage.public_url(item.image_url),
    )


@router.post(
    "/{restaurant_id}/dining-menu/images",
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


@router.put(
    "/{restaurant_id}/menu-categories/re-order",
    response_model=MenuCategoryReorderResponse,
)
async def reorder_menu_categories(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuCategoryReorderRequest,
):

    # data comming from front end is list of category ids in new order
    # {
    # "category_ids": [
    #     "italian_id",
    #     "north_indian_id",
    #     "chinese_id",
    #     "fast_food_id"
    # ]
    # }
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

    result = await db.execute(
        select(MenuCategory)
        .where(MenuCategory.restaurant_id == restaurant_id)
        .order_by(MenuCategory.sort_order.asc())
    )

    menu_categories = result.scalars().all()

    ## menu_categories would be a list of MenuCategory objects
    # [
    #     north_indian_obj,
    #     chinese_obj,
    #     fast_food_obj,
    #     italian_obj
    # ]

    # Dict comp - menu_category is a MenuCategory object
    category_map = {
        menu_category.id: menu_category for menu_category in menu_categories
    }

    ##category_map would look something like this
    # {
    #     "north_indian": north_indian_obj,
    #     "chinese": chinese_obj,
    #     "fast_food": fast_food_obj,
    #     "italian": italian_obj
    # }

    # all the mapped categories for this restraunt is not send by front end
    if len(data.category_ids) != len(menu_categories):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All restaurant categories must be included in the request.",
        )

    # Duplicate ids are sent by the front end
    if len(data.category_ids) != len(set(data.category_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate category IDs are not allowed.",
        )

    # NOTE: checking if the category belongs to the given restaurant
    for category_id in data.category_ids:
        if category_id not in category_map:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category {category_id} is not associated with this restaurant.",
            )

    for index, category_id in enumerate(data.category_ids, start=1):
        category_map[category_id].sort_order = index

    try:

        await db.commit()

    except Exception as exc:

        await db.rollback()

        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the new sorting sorder, check the request and try again",
            # detail=str(exc),
        ) from exc

    return MenuCategoryReorderResponse(
        categories=menu_categories,
        total_categories=len(menu_categories),
        restaurant_id=restaurant_id,
    )


# @router.put(
#     "/{restaurant_id}/menu-categories/re-order",
#     response_model=MenuCategoryReorderResponse,
# )
# async def reorder_menu_categories(
#     restaurant_id: uuid.UUID,
#     current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
#     db: Annotated[AsyncSession, Depends(get_db)],
#     data: MenuCategoryReorderRequest,
# ):
#     # Verify restaurant ownership
#     restaurant = await db.scalar(
#         select(Restaurant).where(
#             Restaurant.id == restaurant_id,
#             Restaurant.owner_id == current_user.id,
#         )
#     )
#     if not restaurant:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Restaurant not found.",
#         )

#     # Fetch all categories for this restaurant
#     result = await db.execute(
#         select(MenuCategory)
#         .where(MenuCategory.restaurant_id == restaurant_id)
#         .with_for_update()  # lock rows to prevent concurrent reorders
#     )
#     menu_categories = result.scalars().all()

#     category_map = {c.id: c for c in menu_categories}

#     # Validate: all categories must be included
#     if len(data.category_ids) != len(menu_categories):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="All restaurant categories must be included in the request.",
#         )

#     # Validate: no duplicate IDs
#     if len(data.category_ids) != len(set(data.category_ids)):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Duplicate category IDs are not allowed.",
#         )

#     # Validate: all IDs belong to this restaurant
#     for category_id in data.category_ids:
#         if category_id not in category_map:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,  # 400, not 409
#                 detail=f"Category {category_id} does not belong to this restaurant.",
#             )

#     try:
#         # Single bulk UPDATE with CASE — one round trip, constraint checked at commit
#         await db.execute(
#             update(MenuCategory)
#             .where(MenuCategory.id.in_(data.category_ids))
#             .values(
#                 sort_order=case(
#                     {
#                         category_id: index
#                         for index, category_id in enumerate(data.category_ids, start=1)
#                     },
#                     value=MenuCategory.id,
#                 )
#             )
#         )

#         await db.commit()

#     except IntegrityError as exc:
#         await db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_409_CONFLICT,
#             detail="Reorder failed due to a sort order conflict. Ensure the constraint is DEFERRABLE.",
#         ) from exc

#     except Exception as exc:
#         await db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to reorder categories.",
#         ) from exc

#     # Refresh to reflect new sort_order values from DB
#     await db.refresh(menu_categories[0])  # triggers session sync
#     result = await db.execute(
#         select(MenuCategory)
#         .where(MenuCategory.restaurant_id == restaurant_id)
#         .order_by(MenuCategory.sort_order.asc())
#     )
#     updated_categories = result.scalars().all()

#     return MenuCategoryReorderResponse(
#         categories=updated_categories,
#         total_categories=len(updated_categories),
#         restaurant_id=restaurant_id,
#     )


@router.get(
    "/{restaurant_id}/menu-categories/{category_id}/items",
    response_model=MenuItemPaginatedResponse,
)
async def get_all_menu_items_for_category_paginated(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.application_per_page,
):
    # Verifying the category exists and belongs to this owner's restaurant
    category = await db.scalar(
        select(MenuCategory).where(
            MenuCategory.id == category_id,
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.status != MenuCategoryStatus.DELETED,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found for this restaurant.",
        )

    # verify restaurant ownership
    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this restaurant.",
        )

    # Using Single query to — fetch items + total count via window function
    count_col = func.count().over().label("total")

    result = await db.execute(
        select(MenuItem, count_col)
        .where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.category_id == category_id,
            MenuItem.status != MenuItemStatus.DELETED,
        )
        .order_by(MenuItem.sort_order.asc())
        .offset(skip)
        .limit(limit)
    )

    rows = result.all()

    total = rows[0][1] if rows else 0
    menu_items = [row[0] for row in rows]

    return MenuItemPaginatedResponse(
        menu_items=menu_items,
        category_id=category_id,
        restaurant_id=restaurant_id,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )


@router.put(
    "/{restaurant_id}/menu-categories/{category_id}/items/re-order",
    response_model=MenuCategoryItemReorderResponse,
)
async def reorder_menu_items_for_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuCategoryItemReorderRequest,
):

    result = await db.execute(
        select(MenuCategory)
        .join(Restaurant)
        .where(
            Restaurant.owner_id == current_user.id,
            MenuCategory.id == category_id,
            MenuCategory.restaurant_id == restaurant_id,
        )
    )

    mapped_category = result.scalars().first()

    if not mapped_category:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Menu category is not found"
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )

    menu_items = result.scalars().all()

    # mapping the item id with MenuItem object
    menu_item_map = {menu_item.id: menu_item for menu_item in menu_items}

    if len(data.menu_item_ids) != len(menu_item_map):

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All menu items mapped to this menu category must be included in the request.",
        )

    if len(data.menu_item_ids) != len(set(data.menu_item_ids)):

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate menu items are not allowed.",
        )

    for menu_item_id in data.menu_item_ids:

        if menu_item_id not in menu_item_map:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more menu_item IDs don't belong to this category.",
            )

    for index, menu_item_id in enumerate(data.menu_item_ids, start=1):

        menu_item_map[menu_item_id].sort_order = index

    try:

        await db.commit()

    except Exception as exc:

        await db.rollback()

        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the new sorting sorder, check the request and try again",
        ) from exc

    return MenuCategoryItemReorderResponse(
        menu_items=menu_items,
        total_items=len(menu_items),
        category_id=category_id,
        restaurant_id=restaurant_id,
    )


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/update",
    response_model=MenuCategoryUpdateResponse,
)
async def update_menu_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuCategoryUpdateRequest,
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.id == category_id,
        )
    )
    category = result.scalars().first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found for this restaurant",
        )

    if category.status == MenuCategoryStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu category is archived. Unarchive it before updating.",
        )

    has_changes = False

    if data.name is not None:
        stripped = data.name.strip()
        normalized = stripped.lower() or None
        if stripped != category.name or normalized != category.normalized_name:
            category.name = stripped
            category.normalized_name = normalized
            has_changes = True

    if data.description is not None:
        stripped = data.description.strip() or None
        if stripped != category.description:
            category.description = stripped
            has_changes = True

    if not has_changes:
        return category

    try:
        await db.commit()
        await db.refresh(category)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the menu category.",
        ) from exc

    return category


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/archive",
    response_model=MenuCategoryArchiveResponse,
)
async def archive_menu_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.id == category_id,
        )
    )
    category = result.scalars().first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found for this restaurant",
        )

    if category.status == MenuCategoryStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu category already archived",
        )

    category.status = MenuCategoryStatus.ARCHIVED
    category.archived_at = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(category)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the menu category.",
        ) from exc

    return category


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/unarchive",
    response_model=MenuCategoryUnarchiveResponse,
)
async def unarchive_menu_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.id == category_id,
        )
    )
    category = result.scalars().first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found for this restaurant",
        )

    if category.status != MenuCategoryStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu category already ACTIVE",
        )

    category.status = MenuCategoryStatus.ACTIVE
    category.archived_at = None

    try:
        await db.commit()
        await db.refresh(category)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unarchive the menu category.",
        ) from exc

    return category


@router.delete(
    "/{restaurant_id}/menu-categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_menu_category(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.id == category_id,
        )
    )
    category = result.scalars().first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found for this restaurant",
        )

    if category.status != MenuCategoryStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archive the category before deleting it.",
        )

    await db.delete(category)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the menu category.",
        ) from exc


@router.delete(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_item_from_menu_category(
    item_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    # restaurant ownership check
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )

    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    # category ownership check

    result = await db.execute(
        select(MenuCategory).where(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.id == category_id,
        )
    )

    category = result.scalars().first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu category not found for this restaurant",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )

    item = result.scalars().first()

    if not item:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu Item not found",
        )

    if item.status != MenuItemStatus.ARCHIVED:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archive the item before deleting it.",
        )

    await db.delete(item)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the menu item.",
        ) from exc


# =========================
# UPDATE MENU ITEM
# =========================


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}",
    response_model=MenuItemUpdateResponse,
)
async def update_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuItemUpdateRequest,
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status == MenuItemStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu item is archived. Unarchive it before updating.",
        )

    if item.status == MenuItemStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    has_changes = False

    if data.name is not None:
        stripped = data.name.strip()
        normalized = stripped.lower() or None
        if stripped != item.name or normalized != item.normalized_name:
            item.name = stripped
            item.normalized_name = normalized
            has_changes = True

    if data.description is not None:
        stripped = data.description.strip() or None
        if stripped != item.description:
            item.description = stripped
            has_changes = True

    if data.price is not None:
        if data.price != item.price:
            item.price = data.price
            has_changes = True

    if data.discounted_price is not None:
        if data.discounted_price != item.discounted_price:
            # discounted price must be less than base price
            effective_price = data.price if data.price is not None else item.price
            if data.discounted_price >= effective_price:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Discounted price must be less than the base price.",
                )
            item.discounted_price = data.discounted_price
            has_changes = True

    # explicit null to clear discounted price
    if data.clear_discounted_price is True and item.discounted_price is not None:
        item.discounted_price = None
        has_changes = True

    if data.veg_type is not None:
        if data.veg_type != item.veg_type:
            item.veg_type = data.veg_type
            has_changes = True

    if data.preparation_time_minutes is not None:
        if data.preparation_time_minutes != item.preparation_time_minutes:
            item.preparation_time_minutes = data.preparation_time_minutes
            has_changes = True

    if data.calories is not None:
        if data.calories != item.calories:
            item.calories = data.calories
            has_changes = True

    if not has_changes:
        return item

    try:
        await db.commit()
        await db.refresh(item)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A menu item with this name already exists in this category.",
        ) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the menu item.",
        ) from exc

    return item


# =========================
# TOGGLE ITEM AVAILABILITY
# =========================


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}/availability",
    response_model=MenuItemUpdateResponse,
)
async def toggle_menu_item_availability(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: MenuItemAvailabilityRequest,
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status == MenuItemStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu item is archived. Unarchive it before changing availability.",
        )

    if item.status == MenuItemStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if data.is_available == item.is_available:
        return item

    item.is_available = data.is_available

    try:
        await db.commit()
        await db.refresh(item)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update item availability.",
        ) from exc

    return item


# =========================
# ARCHIVE MENU ITEM
# =========================


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}/archive",
    response_model=MenuItemUpdateResponse,
)
async def archive_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status == MenuItemStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status == MenuItemStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu item is already archived.",
        )

    item.status = MenuItemStatus.ARCHIVED
    item.archived_at = datetime.now(UTC)
    # archived items should not be orderable
    item.is_available = False

    try:
        await db.commit()
        await db.refresh(item)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to archive the menu item.",
        ) from exc

    return item


# =========================
# UNARCHIVE MENU ITEM
# =========================


@router.patch(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}/unarchive",
    response_model=MenuItemUpdateResponse,
)
async def unarchive_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status == MenuItemStatus.DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status != MenuItemStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Menu item is already active.",
        )

    item.status = MenuItemStatus.ACTIVE
    item.archived_at = None
    # restore as unavailable — owner should explicitly re-enable
    item.is_available = False

    try:
        await db.commit()
        await db.refresh(item)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unarchive the menu item.",
        ) from exc

    return item


# =========================
# DELETE MENU ITEM
# (fix of existing broken route)
# =========================


@router.delete(
    "/{restaurant_id}/menu-categories/{category_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_menu_item(
    restaurant_id: uuid.UUID,
    category_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.id == item_id,
            MenuItem.category_id == category_id,
            MenuItem.restaurant_id == restaurant_id,
        )
    )
    item = result.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Menu item not found for this category",
        )

    if item.status != MenuItemStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archive the item before deleting it.",
        )

    await db.delete(item)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the menu item.",
        ) from exc
