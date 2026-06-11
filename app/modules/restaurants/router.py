from __future__ import annotations

import asyncio
import logging
import uuid
from asyncio import gather
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Annotated, List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.constants import (
    RESTAURANT_FOOD_IMAGE_STORAGE_PREFIX,
    RESTAURANT_IMAGES_PREFIX,
)
from app.core.dependencies import require_roles
from app.core.image_processing import ImageProcessingError, _image_key, process_image
from app.core.storage import StorageBackend, _cleanup_keys, get_storage
from app.db.database import get_db
from app.modules.restaurants.models import (
    AvailabilityStatus,
    CuisineRequest,
    CuisineStatus,
    CuisineType,
    MappedCuisineStatus,
    Restaurant,
    RestaurantAvailability,
    RestaurantClosure,
    RestaurantCuisineMapping,
    RestaurantImage,
    RestaurantImageType,
    RestaurantStatus,
)
from app.modules.restaurants.schemas import (
    ClosureCreate,
    ClosureResponse,
    CreateCuisine,
    CuisineAdd,
    CuisineAddResponse,
    CuisineListResponse,
    CuisineResponse,
    DayHoursResponse,
    DayHoursUpdate,
    RestaurantByCityPaginatedResponse,
    RestaurantCreate,
    RestaurantCreateResponse,
    RestaurantCuisineListResponse,
    RestaurantCuisineRequestListResponse,
    RestaurantDocumentsUpload,
    RestaurantDocumentsUploadResponse,
    RestaurantHoursResponse,
    RestaurantHoursUpload,
    RestaurantImageUploadResponse,
    RestaurantPauseSchema,
    RestaurantPendingCuisineItem,
    RestaurantPrimaryCuisineResponse,
    RestaurantPrimaryCuisneRequest,
    RestaurantPrimaryImageResponse,
    RestaurantSchema,
)
from app.modules.restaurants.utils import (  # generates unique slug for restaurant; generates unique slugs for cuisine name
    _build_availability_rows,
    _get_owned_restaurant,
    _get_upsert_fn,
    generate_unique_slug,
    normalize,
    normalize_cuisine_name,
    slugify,
)
from app.modules.users.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


# Constants


MAX_FILES_PER_REQUEST = settings.max_restaurant_images_per_request
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# RESTAURANT_IMAGES_PREFIX = "restaurant_images"


# Create restaurant draft


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

    # normalize = strip().lower()
    normalized_name = normalize(data.name)
    normalized_address_line_1 = normalize(data.address_line_1)
    normalized_city = normalize(data.city)

    duplicate = await db.scalar(
        select(Restaurant).where(
            Restaurant.owner_id == current_user.id,
            Restaurant.normalized_name == normalized_name,
            Restaurant.normalized_address_line_1 == normalized_address_line_1,
            Restaurant.normalized_city == normalized_city,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A restaurant with the same name and address already exists for this owner.",
        )

    slug = await generate_unique_slug(db, data.name, data.city)

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
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.refresh(new_restaurant)
    return new_restaurant


# Upload documents


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
    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Restaurant not found for this owner."
        )

    restaurant.fssai_license_number = data.fssai_license_number
    restaurant.gst_number = data.gst_number
    restaurant.status = RestaurantStatus.DOCUMENTS_ADDED

    db.add(restaurant)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Error updating restaurant documents."
        ) from exc

    await db.refresh(restaurant)
    return restaurant


# Upload images


@router.post(
    "/{restaurant_id}/images",
    response_model=RestaurantImageUploadResponse,
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
async def upload_restaurant_images(
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
                RestaurantImage.restaurant_id == restaurant_id
            )
        )
        or 0
    )

    # Used when Restraunts has storage limits - for dev applying storage limits
    remaining_slots = settings.max_images_per_restaurant - existing_count
    if remaining_slots <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Restaurant already has the maximum of "
            f"{settings.max_images_per_restaurant} images.",
        )
    if len(files) > remaining_slots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {remaining_slots} image slot(s) remaining "
            f"(max {settings.max_images_per_restaurant} total).",
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

        key = _image_key(restaurant_id, filename, RESTAURANT_IMAGES_PREFIX)
        processed.append((jpeg_bytes, key))

    uploaded_keys: list[str] = []
    try:
        upload_tasks = [storage.upload(data, key) for data, key in processed]
        await asyncio.gather(*upload_tasks)
        uploaded_keys = [key for _, key in processed]

    except Exception as exc:

        await _cleanup_keys(storage, uploaded_keys)
        logger.exception("Storage upload failed for restaurant %s", restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed. Please try again.",
        ) from exc

    db_images = [
        RestaurantImage(
            restaurant_id=restaurant_id,
            image_url=key,
        )
        for key in uploaded_keys
    ]

    db.add_all(db_images)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await _cleanup_keys(storage, uploaded_keys)
        logger.exception("DB commit failed for restaurant %s images", restaurant_id)
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


@router.patch(
    "/{restaurant_id}/primary-image",
    response_model=RestaurantPrimaryImageResponse,
)
async def upload_primary_image_for_restaurant(
    restaurant_id: uuid.UUID,
    image: Annotated[UploadFile, File(description="Menu item image (JPEG/PNG/WEBP)")],
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
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
            detail="restaurnat not found for this owner",
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

    key = _image_key(restaurant_id, filename, RESTAURANT_IMAGES_PREFIX)

    try:
        await storage.upload(jpeg_bytes, key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed.",
        ) from exc

    result = await db.execute(
        select(RestaurantImage).where(
            RestaurantImage.restaurant_id == restaurant_id,
            RestaurantImage.is_primary == True,
        )
    )

    old_primary_image = result.scalars().first()
    old_key = None

    if old_primary_image:

        # old_primary_image.is_primary = False

        old_key = old_primary_image.image_url

        # delete(old_primary_image)

        await db.delete(old_primary_image)
        await db.flush()

    new_primary_image = RestaurantImage(
        restaurant_id=restaurant_id,
        image_url=key,
        is_primary=True,
    )
    db.add(new_primary_image)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()

        await _cleanup_keys(storage, [key])

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # detail="Failed to save image information.",
            detail=str(exc),
        ) from exc

    await db.refresh(new_primary_image)

    if old_key:
        try:
            await storage.delete(old_key)
        except Exception:
            pass

    return RestaurantPrimaryImageResponse(
        id=new_primary_image.id,
        image_path=storage.public_url(new_primary_image.image_url),
    )


@router.post(
    "/{restaurant_id}/food-images",
    response_model=RestaurantImageUploadResponse,
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
async def upload_restaurant_food_images(
    restaurant_id: uuid.UUID,
    files: Annotated[
        List[UploadFile], File(description="Restaurant food (JPEG/PNG/WEBP)")
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
                RestaurantImage.restaurant_id == restaurant_id
            )
        )
        or 0
    )

    # Used when Restraunts has storage limits - for dev applying storage limits
    remaining_slots = settings.max_restaurant_food_images_per_request - existing_count
    if remaining_slots <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Restaurant already has the maximum of "
            f"{settings.max_restaurant_food_images_per_request} images.",
        )
    if len(files) > remaining_slots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {remaining_slots} image slot(s) remaining "
            f"(max {settings.max_restaurant_food_images_per_request} total).",
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

        key = _image_key(restaurant_id, filename, RESTAURANT_FOOD_IMAGE_STORAGE_PREFIX)
        processed.append((jpeg_bytes, key))

    uploaded_keys: list[str] = []
    try:
        upload_tasks = [storage.upload(data, key) for data, key in processed]
        await asyncio.gather(*upload_tasks)
        uploaded_keys = [key for _, key in processed]

    except Exception as exc:

        await _cleanup_keys(storage, uploaded_keys)
        logger.exception("Storage upload failed for restaurant %s", restaurant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Image upload to storage failed. Please try again.",
        ) from exc

    db_images = [
        RestaurantImage(
            restaurant_id=restaurant_id,
            image_url=key,
            image_type=RestaurantImageType.FOOD_GALLERY,
        )
        for key in uploaded_keys
    ]

    db.add_all(db_images)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await _cleanup_keys(storage, uploaded_keys)
        logger.exception("DB commit failed for restaurant %s images", restaurant_id)
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


@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_restaurant(
    restaurant_id: uuid.UUID,
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Restaurant not found.")

    image_keys_result = await db.execute(
        select(RestaurantImage.image_url).where(
            RestaurantImage.restaurant_id == restaurant_id
        )
    )
    image_keys = [row[0] for row in image_keys_result.all()]

    await db.delete(restaurant)
    await db.commit()

    if image_keys:
        await _cleanup_keys(storage, image_keys)


@router.post(
    "/{restaurant_id}/hours",
    response_model=RestaurantHoursResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set restaurant hours (onboarding)",
    description=(
        "Sets the full weekly availability schedule. "
        "All 7 days must be provided — existing schedule is replaced entirely. "
        "Use PATCH /{restaurant_id}/hours/{day} to update a single day after onboarding."
    ),
)
async def create_restaurant_hours(
    restaurant_id: uuid.UUID,
    data: RestaurantHoursUpload,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    # delete all existing shifts for this restaurant — full replacement
    await db.execute(
        delete(RestaurantAvailability).where(
            RestaurantAvailability.restaurant_id == restaurant_id
        )
    )

    new_rows = [
        RestaurantAvailability(
            restaurant_id=restaurant_id,
            day_of_week=shift.day_of_week,
            status=shift.status,
            opening_time=shift.opening_time,
            closing_time=shift.closing_time,
            shift_index=shift.shift_index,
        )
        for shift in data.hours
    ]

    db.add_all(new_rows)
    restaurant.status = RestaurantStatus.TIMINGS_ADDED

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Hours insert integrity error for restaurant %s: %s", restaurant_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hours data. Check for constraint violations.",
        ) from exc

    result = await db.execute(
        select(RestaurantAvailability)
        .where(RestaurantAvailability.restaurant_id == restaurant_id)
        .order_by(
            RestaurantAvailability.day_of_week,
            RestaurantAvailability.shift_index,
        )
    )
    hours = result.scalars().all()

    return RestaurantHoursResponse(hours=hours)


@router.patch(
    "/{restaurant_id}/hours/{day}",
    response_model=DayHoursResponse,
    status_code=status.HTTP_200_OK,
    summary="Update hours for a specific day",
    description=(
        "Replaces all shifts for a single day atomically (delete + insert). "
        "Send a single shift with status=CLOSED to mark the day closed. "
        "day parameter: 0=Monday … 6=Sunday."
    ),
)
async def update_day_hours(
    restaurant_id: uuid.UUID,
    day: Annotated[
        int, Path(ge=0, le=6, description="Day of week: 0=Monday, 6=Sunday")
    ],
    data: DayHoursUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_restaurant(restaurant_id, current_user.id, db)

    wrong_day = [s for s in data.shifts if s.day_of_week != day]
    if wrong_day:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"All shifts must be for day {day}. "
                f"Found shifts for day(s): {sorted({s.day_of_week for s in wrong_day})}."
            ),
        )

    try:

        await db.execute(
            delete(RestaurantAvailability).where(
                RestaurantAvailability.restaurant_id == restaurant_id,
                RestaurantAvailability.day_of_week == day,
            )
        )

        new_rows = [
            RestaurantAvailability(
                restaurant_id=restaurant_id,
                day_of_week=shift.day_of_week,
                status=shift.status,
                opening_time=shift.opening_time,
                closing_time=shift.closing_time,
                shift_index=shift.shift_index,
            )
            for shift in data.shifts
        ]

        db.add_all(new_rows)
        await db.commit()

    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Day hours update integrity error — restaurant %s day %s: %s",
            restaurant_id,
            day,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hours data. Check for constraint violations.",
        ) from exc

    for row in new_rows:
        await db.refresh(row)

    return DayHoursResponse(day_of_week=day, shifts=new_rows)


# POST /{restaurant_id}/closure
# Temporarily close the restaurant


# ── MANUAL PAUSE ──────────────────────────────────────────


@router.patch(
    "/{restaurant_id}/pause",
    response_model=RestaurantSchema,
    status_code=status.HTTP_200_OK,
    summary="Pause order intake immediately",
    description="Instantly hides the restaurant from customers. No end date — owner must resume manually.",
)
async def pause_restaurant(
    restaurant_id: uuid.UUID,
    data: RestaurantPauseSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    if restaurant.status != RestaurantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active restaurants can be paused.",
        )
    if restaurant.is_manually_paused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restaurant is already paused.",
        )

    restaurant.is_manually_paused = True
    restaurant.pause_reason = data.reason
    restaurant.paused_at = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(restaurant)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to pause restaurant.",
        ) from exc

    return restaurant


@router.patch(
    "/{restaurant_id}/resume",
    response_model=RestaurantSchema,
    status_code=status.HTTP_200_OK,
    summary="Resume order intake",
    description="Makes the restaurant visible to customers again after a manual pause.",
)
async def resume_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    if restaurant.status != RestaurantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active restaurants can be resumed.",
        )
    if not restaurant.is_manually_paused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restaurant is not paused.",
        )

    restaurant.is_manually_paused = False
    restaurant.pause_reason = None
    restaurant.paused_at = None

    try:
        await db.commit()
        await db.refresh(restaurant)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resume restaurant.",
        ) from exc

    return restaurant


# ── PLANNED CLOSURE ───────────────────────────────────────


@router.post(
    "/{restaurant_id}/closure",
    response_model=ClosureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a planned closure",
    description=(
        "Creates a planned closure starting from midnight today (UTC). "
        "end_date is the last day of closure (inclusive) — restaurant reopens at midnight after that date. "
        "end_date=null means indefinite — call DELETE /closure to reopen. "
        "Does NOT affect is_manually_paused."
    ),
)
async def create_closure(
    restaurant_id: uuid.UUID,
    data: ClosureCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    if restaurant.status != RestaurantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active restaurants can have closures.",
        )

    now = datetime.now(UTC)

    # starts_at — midnight of today in UTC
    # owner clicks the button today, closure starts from the beginning of today
    starts_at = datetime.combine(now.date(), time.min, tzinfo=UTC)

    # ends_at — midnight of the day AFTER end_date (exclusive upper bound)
    # "closed until June 25" means visible again at 00:00 June 26
    ends_at = (
        datetime.combine(data.end_date, time.min, tzinfo=UTC) + timedelta(days=1)
        if data.end_date is not None
        else None
    )

    existing = await db.scalar(
        select(RestaurantClosure).where(
            RestaurantClosure.restaurant_id == restaurant_id,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active closure already exists. Remove it before creating a new one.",
        )

    closure = RestaurantClosure(
        restaurant_id=restaurant_id,
        reason=data.reason,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(closure)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create closure.",
        ) from exc

    await db.refresh(closure)
    return closure


@router.delete(
    "/{restaurant_id}/closure",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel an active planned closure",
    description=(
        "Removes the active closure record. " "Does NOT affect is_manually_paused."
    ),
)
async def delete_closure(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_restaurant(restaurant_id, current_user.id, db)

    now = datetime.now(UTC)

    active_closure = await db.scalar(
        select(RestaurantClosure).where(
            RestaurantClosure.restaurant_id == restaurant_id,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
    )
    if not active_closure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active closure found for this restaurant.",
        )

    await db.delete(active_closure)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove closure.",
        ) from exc


@router.post(
    "/{restaurant_id}/cuisine/request",
    response_model=CuisineResponse,
)
async def request_new_cuisine(
    restaurant_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.RESTAURANT_OWNER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: CreateCuisine,
):

    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    name = data.cuisine_name

    # just text.split().lower()
    normalized_name = normalize_cuisine_name(name)
    slug = slugify(normalized_name)

    result = await db.execute(
        select(CuisineType).where(
            CuisineType.cuisine_slug == slug, CuisineType.status == CuisineStatus.ACTIVE
        )
    )

    exisiting_cuisine = result.scalars().first()

    if exisiting_cuisine:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cuisine name already exists {exisiting_cuisine.cuisine_slug}",
        )

    pending_result = await db.execute(
        select(CuisineRequest).where(CuisineRequest.cuisine_slug == slug)
    )

    # allowing multiple requests for same pending cuisines,
    # but creating only one request in the CuisineRequest
    pending_cuisine = pending_result.scalars().first()

    if not pending_cuisine:

        new_request = CuisineRequest(
            requested_by=current_user.id,
            cuisine_name=normalized_name,
            cuisine_slug=slug,
        )

        try:
            db.add(new_request)
            await db.commit()

        except IntegrityError as exe:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Something went wrong, Please check if the cuisine already exists",
            )
        await db.refresh(new_request)

    new_cuisine_mappping = RestaurantCuisineMapping(
        restaurant_id=restaurant_id,
        request_id=new_request.id if not pending_cuisine else pending_cuisine.id,
        # cuisine_name=normalized_name,
        # cuisine_slug=slug,
        status=MappedCuisineStatus.PENDING_REVIEW,  # new-request.status
    )

    try:
        db.add(new_cuisine_mappping)
        await db.commit()

    except IntegrityError as exe:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restaurant already requested same pending cuisine",
        )
    await db.refresh(new_request)

    return new_request


@router.patch(
    "/{restaurant_id}/primary-cuisine",
    response_model=RestaurantPrimaryCuisineResponse,
)
async def set_primary_cuisine_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.RESTAURANT_OWNER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: RestaurantPrimaryCuisneRequest,
):

    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
            RestaurantCuisineMapping.is_primary == True,
        )
    )

    existing_primary_cuisine = result.scalars().first()

    if existing_primary_cuisine:

        if existing_primary_cuisine.cuisine_id == data.cuisine_id:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Given cuisine type already uploaded as primary cuisine type.",
            )

        existing_primary_cuisine.is_primary = False

        await db.flush()
        # await db.delete(existing_primary_cuisine)

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
            RestaurantCuisineMapping.cuisine_id == data.cuisine_id,
        )
    )

    existing_cuisine = result.scalars().first()

    primary_cuisine_mapping = None

    if existing_cuisine:

        if existing_cuisine.status != MappedCuisineStatus.ACTIVE:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pending Cuisine requests can't be set as primary cuisine.",
            )

        existing_cuisine.is_primary = True

        primary_cuisine_mapping = existing_cuisine

    else:

        result = await db.execute(
            select(CuisineType).where(
                CuisineType.id == data.cuisine_id,
                CuisineType.status == CuisineStatus.ACTIVE,
            )
        )

        cuisine = result.scalars().first()

        if not cuisine:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cuisine Type not found.",
            )

        new_primary_cuisine = RestaurantCuisineMapping(
            restaurant_id=restaurant_id,
            cuisine_id=cuisine.id,
            status=MappedCuisineStatus.ACTIVE,
            is_primary=True,
        )
        db.add(new_primary_cuisine)

        primary_cuisine_mapping = new_primary_cuisine

    try:

        await db.commit()

    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another primary cuisine is already set. Try again.",
        ) from exc

    result = await db.execute(
        select(RestaurantCuisineMapping)
        .options(selectinload(RestaurantCuisineMapping.cuisine))
        .where(RestaurantCuisineMapping.id == primary_cuisine_mapping.id)
    )
    return result.scalars().first()


@router.patch(
    "/{restaurant_id}/cuisine",
)
async def upload_cuisine_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.RESTAURANT_OWNER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: CuisineAdd,
):

    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(CuisineType).where(CuisineType.id == data.cuisine_id)
    )

    cuisine = result.scalars().first()

    if not cuisine or cuisine.status == CuisineStatus.REVOKED:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine Type not found",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.cuisine_id == cuisine.id,
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
        )
    )

    exisiting_cuisine = result.scalars().first()

    if exisiting_cuisine:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cuisine Type already exists for this restaurant",
        )

    new_mapping = RestaurantCuisineMapping(
        restaurant_id=restaurant_id,
        cuisine_id=cuisine.id,
        status=MappedCuisineStatus.ACTIVE,
    )
    db.add(new_mapping)

    try:

        await db.commit()

    except IntegrityError as exe:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restaurant already requested same pending cuisine",
        )
    await db.refresh(new_mapping)

    return CuisineAddResponse(
        id=new_mapping.id,
        cuisine_id=cuisine.id,
        cuisine_name=cuisine.cuisine_name,
        cuisine_slug=cuisine.cuisine_slug,
        status=new_mapping.status,
        created_at=new_mapping.created_at,
    )


# =========================
# GET ALL APPROVED CUISINES
# (browse catalog before adding)
# =========================


@router.get(
    "/cuisines",
    response_model=CuisineListResponse,
)
async def get_all_approved_cuisines(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    search: Annotated[str | None, Query(max_length=100)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[
        int, Query(ge=1, le=100)
    ] = settings.approved_cuisine_names_per_page,
):
    """
    Returns all ACTIVE approved cuisines.
    Used by the owner to browse and pick cuisines to add to their restaurant.
    Supports optional fuzzy name search.
    """
    base_query = select(CuisineType).where(CuisineType.status == CuisineStatus.ACTIVE)

    if search:
        normalized_search = normalize_cuisine_name(search)
        base_query = base_query.where(
            CuisineType.cuisine_name.ilike(f"%{normalized_search}%")
        )

    count_result = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result or 0

    result = await db.execute(
        base_query.order_by(CuisineType.cuisine_name.asc()).offset(skip).limit(limit)
    )
    cuisines = result.scalars().all()

    return CuisineListResponse(
        cuisines=cuisines,
        total=total,
        skip=skip,
        limit=limit,
        has_more=skip + limit < total,
    )


# =========================
# GET ALL CUISINES FOR A RESTAURANT
# (mapped cuisines — both active and pending)
# =========================


@router.get(
    "/{restaurant_id}/cuisines",
    response_model=RestaurantCuisineListResponse,
)
async def get_cuisines_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns all cuisine mappings for a restaurant — active and pending.
    Loads the related CuisineType and CuisineRequest eagerly to avoid N+1.
    """
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping)
        .options(
            selectinload(RestaurantCuisineMapping.cuisine),
        )
        .where(RestaurantCuisineMapping.restaurant_id == restaurant_id)
        .order_by(
            RestaurantCuisineMapping.is_primary.desc(),
            RestaurantCuisineMapping.created_at.asc(),
        )
    )
    mappings = result.scalars().all()

    return RestaurantCuisineListResponse(
        cuisines=mappings,
        total=len(mappings),
        restaurant_id=restaurant_id,
    )


# =========================
# GET ALL PENDING CUISINE REQUESTS
# FOR A RESTAURANT
# =========================


@router.get(
    "/{restaurant_id}/cuisine/requests",
    response_model=RestaurantCuisineRequestListResponse,
)
async def get_pending_cuisine_requests_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns all PENDING_REVIEW cuisine mappings for a restaurant,
    joined with the underlying CuisineRequest for name/slug details.
    """
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping, CuisineRequest)
        .join(
            CuisineRequest,
            RestaurantCuisineMapping.request_id == CuisineRequest.id,
        )
        .where(
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
            RestaurantCuisineMapping.status == MappedCuisineStatus.PENDING_REVIEW,
        )
        .order_by(RestaurantCuisineMapping.created_at.asc())
    )
    rows = result.all()

    return RestaurantCuisineRequestListResponse(
        requests=[
            RestaurantPendingCuisineItem(
                mapping_id=mapping.id,
                request_id=request.id,
                cuisine_name=request.cuisine_name,
                cuisine_slug=request.cuisine_slug,
                status=mapping.status,
                is_primary=mapping.is_primary,
                created_at=mapping.created_at,
            )
            for mapping, request in rows
        ],
        total=len(rows),
        restaurant_id=restaurant_id,
    )


# =========================
# REMOVE AN APPROVED CUISINE
# FROM RESTAURANT
# =========================


@router.delete(
    "/{restaurant_id}/cuisine/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_cuisine_from_restaurant(
    restaurant_id: uuid.UUID,
    mapping_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Removes an approved cuisine mapping from a restaurant.
    Cannot remove a primary cuisine — demote it first via PATCH /primary-cuisine.
    Cannot remove a pending cuisine — cancel via DELETE /cuisine/request/{mapping_id}.
    """
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.id == mapping_id,
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
        )
    )
    mapping = result.scalars().first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine mapping not found for this restaurant.",
        )

    if mapping.status == MappedCuisineStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove a pending cuisine. Cancel the request instead via DELETE /cuisine/request/{mapping_id}.",
        )

    if mapping.is_primary:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the primary cuisine. Set a different primary cuisine first.",
        )

    await db.delete(mapping)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove cuisine.",
        ) from exc


# =========================
# CANCEL A PENDING CUISINE REQUEST
# =========================


@router.delete(
    "/{restaurant_id}/cuisine/request/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_pending_cuisine_request(
    restaurant_id: uuid.UUID,
    mapping_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Cancels a pending cuisine request for a restaurant by removing
    the mapping row. Does NOT delete the underlying CuisineRequest —
    other restaurants may have mapped to the same request.
    Only works on PENDING_REVIEW mappings.
    """
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.id == mapping_id,
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
        )
    )
    mapping = result.scalars().first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine request mapping not found for this restaurant.",
        )

    if mapping.status != MappedCuisineStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending cuisine requests can be cancelled. Use DELETE /cuisine/{mapping_id} for approved cuisines.",
        )

    if mapping.is_primary:
        # defensive — pending cuisines shouldn't be primary, but guard it
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot cancel a primary cuisine mapping.",
        )

    await db.delete(mapping)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel cuisine request.",
        ) from exc


# =========================
# DEMOTE PRIMARY CUISINE
# (unset is_primary without removing)
# =========================


@router.delete(
    "/{restaurant_id}/primary-cuisine",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def demote_primary_cuisine(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Unsets the primary cuisine flag for a restaurant without removing the mapping.
    Use this before removing the primary cuisine or reassigning a new one.
    """
    result = await db.execute(
        select(Restaurant.id).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user.id,
        )
    )
    if not result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner.",
        )

    result = await db.execute(
        select(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.restaurant_id == restaurant_id,
            RestaurantCuisineMapping.is_primary == True,
        )
    )
    primary_mapping = result.scalars().first()

    if not primary_mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No primary cuisine set for this restaurant.",
        )

    primary_mapping.is_primary = False

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to demote primary cuisine.",
        ) from exc


@router.get("/", response_model=RestaurantByCityPaginatedResponse)
async def get_all_restaurants_for_city(
    city: Annotated[str, Query(min_length=2, max_length=50)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.restaurants_per_page,
):
    now = datetime.now(UTC)
    current_time = now.time().replace(tzinfo=None)
    today_dow = now.isoweekday() % 7  # convert to 0=Monday..6=Sunday

    normalized = normalize(city)  # same normalize() used at creation time

    # restaurants under active planned closure right now
    active_closure_subquery = (
        select(RestaurantClosure.restaurant_id)
        .where(
            RestaurantClosure.starts_at <= now,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
        .scalar_subquery()
    )

    filters = [
        Restaurant.normalized_city
        == normalized,  # correct: normalized input vs normalized column
        Restaurant.status == RestaurantStatus.ACTIVE,
        Restaurant.is_manually_paused.is_(False),  # manual pause check
        Restaurant.id.not_in(active_closure_subquery),  # planned closure check
        RestaurantAvailability.restaurant_id == Restaurant.id,
        RestaurantAvailability.day_of_week == today_dow,
        RestaurantAvailability.status == AvailabilityStatus.OPEN,
        RestaurantAvailability.opening_time <= current_time,
        RestaurantAvailability.closing_time > current_time,
    ]

    count_query = (
        select(func.count(Restaurant.id))
        .join(
            RestaurantAvailability,
            RestaurantAvailability.restaurant_id == Restaurant.id,
        )
        .where(*filters)
    )

    data_query = (
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
        .where(*filters)
        .order_by(Restaurant.avg_rating.desc())
        .offset(skip)
        .limit(limit)
    )

    total, data_result = await gather(
        db.scalar(count_query),
        db.execute(data_query),
    )

    restaurants = data_result.scalars().all()

    return RestaurantByCityPaginatedResponse(
        restaurants=restaurants,
        total=total or 0,
        skip=skip,
        limit=limit,
        has_more=skip + len(restaurants) < (total or 0),
    )


@router.post(
    "/{restaurant_id}/activate",
)
async def activate_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.owner_id == current_user.id,
            Restaurant.id == restaurant_id,
        )
    )

    restaurant = result.scalars().first()

    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="restaurant not found for this owner",
        )

    if restaurant.status != RestaurantStatus.MENU_ADDED:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Added atleast a menu item to activate the restaurant",
        )

    restaurant.status = RestaurantStatus.ACTIVE
    restaurant.is_activated = True
    restaurant.activated_at = datetime.now(UTC)

    try:
        await db.commit()
        await db.refresh(restaurant)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate the restaurant.",
        ) from exc

    return restaurant


@router.get(
    "/{restaurant_id}",
)
async def get_detailed_restaurant_by_id(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Restaurant)
        .options(selectinload(Restaurant.primary_image))
        .where(
            Restaurant.id == restaurant_id,
        )
    )

    restaurant = result.scalars().first()

    return restaurant
