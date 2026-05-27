from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.restaurants.models import (
    Restaurant,
    RestaurantAvailability,
    RestaurantClosure,
    RestaurantImage,
    RestaurantStatus,
)
from app.modules.restaurants.schemas import (
    ClosureCreate,
    ClosureResponse,
    DayHoursResponse,
    DayHoursUpdate,
    RestaurantCreate,
    RestaurantCreateResponse,
    RestaurantDocumentsUpload,
    RestaurantDocumentsUploadResponse,
    RestaurantHoursResponse,
    RestaurantHoursUpload,
    RestaurantImageUploadResponse,
)
from app.modules.restaurants.storage import StorageBackend, get_storage
from app.modules.restaurants.utils import (
    ImageProcessingError,
    _build_availability_rows,
    _get_owned_restaurant,
    _get_upsert_fn,
    generate_unique_slug,
    normalize,
    process_image,
)
from app.modules.users.models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


# Constants


MAX_FILES_PER_REQUEST = 5
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

RESTAURANT_IMAGES_PREFIX = "restaurant_images"


def _image_key(restaurant_id: uuid.UUID, filename: str) -> str:
    """Stable, collision-free storage key for a restaurant image."""
    return f"{RESTAURANT_IMAGES_PREFIX}/{restaurant_id}/{filename}"


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

        key = _image_key(restaurant_id, filename)
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
            # detail="Failed to save image records. Uploaded files have been removed.",
            detail=str(exc),
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


async def _cleanup_keys(storage: StorageBackend, keys: list[str]) -> None:
    """Delete storage objects without raising — used in error-recovery paths."""
    results = await asyncio.gather(
        *[storage.delete(k) for k in keys],
        return_exceptions=True,
    )
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("Cleanup failed for key %r: %s", key, result)


# Set primary image


@router.patch(
    "/{restaurant_id}/images/{image_id}/make-primary",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_primary_restaurant_image(
    restaurant_id: uuid.UUID,
    image_id: uuid.UUID,
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Restaurant not found.")

    image = await db.scalar(
        select(RestaurantImage).where(
            RestaurantImage.id == image_id,
            RestaurantImage.restaurant_id == restaurant_id,
        )
    )
    if not image:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Image not found.")

    await db.execute(
        update(RestaurantImage)
        .where(RestaurantImage.restaurant_id == restaurant_id)
        .values(is_primary=False)
    )
    await db.execute(
        update(RestaurantImage)
        .where(RestaurantImage.id == image_id)
        .values(is_primary=True)
    )
    await db.commit()


# ==================
# Delete restaurant
# ==================


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
        "Upserts the weekly availability schedule. Safe to call multiple times "
        "during onboarding — existing shifts for submitted days are overwritten. "
        "Days not included in the payload are left untouched."
    ),
)
async def create_restaurant_hours(
    restaurant_id: uuid.UUID,
    data: RestaurantHoursUpload,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_restaurant(restaurant_id, current_user.id, db)

    rows = _build_availability_rows(restaurant_id, data.hours)

    dialect_insert = _get_upsert_fn()

    stmt = dialect_insert(RestaurantAvailability).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["restaurant_id", "day_of_week", "shift_index"],
        set_={
            "status": stmt.excluded.status,
            "opening_time": stmt.excluded.opening_time,
            "closing_time": stmt.excluded.closing_time,
            "updated_at": datetime.now(UTC),
        },
    )

    try:
        await db.execute(stmt)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Hours upsert integrity error for restaurant %s: %s", restaurant_id, exc
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


# POST /{restaurant_id}/hours
# Onboarding step — set the full weekly schedule


@router.post(
    "/{restaurant_id}/hours",
    response_model=RestaurantHoursResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set restaurant hours (onboarding)",
    description=(
        "Upserts the weekly availability schedule. Safe to call multiple times "
        "during onboarding — existing shifts for submitted days are overwritten. "
        "Days not included in the payload are left untouched."
    ),
)
async def create_restaurant_hours(
    restaurant_id: uuid.UUID,
    data: RestaurantHoursUpload,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_owned_restaurant(restaurant_id, current_user.id, db)

    rows = _build_availability_rows(restaurant_id, data.hours)

    dialect_insert = _get_upsert_fn()

    stmt = dialect_insert(RestaurantAvailability).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["restaurant_id", "day_of_week", "shift_index"],
        set_={
            "status": stmt.excluded.status,
            "opening_time": stmt.excluded.opening_time,
            "closing_time": stmt.excluded.closing_time,
            "updated_at": datetime.now(UTC),
        },
    )

    try:
        await db.execute(stmt)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Hours upsert integrity error for restaurant %s: %s", restaurant_id, exc
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


#
# PATCH /{restaurant_id}/hours/{day}
# Update one day — replaces ALL shifts for that day atomically


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


@router.post(
    "/{restaurant_id}/closure",
    response_model=ClosureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Temporarily close a restaurant",
    description=(
        "Creates a closure event. The restaurant is immediately hidden from "
        "customers and no new orders can be placed. "
        "ends_at=null means indefinite — call DELETE /closure to reopen. "
        "ends_at set to a future datetime schedules an automatic reopen."
    ),
)
async def create_closure(
    restaurant_id: uuid.UUID,
    data: ClosureCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    now = datetime.now(UTC)
    existing_closure = await db.scalar(
        select(RestaurantClosure).where(
            RestaurantClosure.restaurant_id == restaurant_id,
            RestaurantClosure.starts_at <= now,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
    )
    if existing_closure:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Restaurant already has an active closure. "
                "Call DELETE /closure to remove it before creating a new one."
            ),
        )

    closure = RestaurantClosure(
        restaurant_id=restaurant_id,
        reason=data.reason,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
    )

    restaurant.is_manually_closed = True

    db.add(closure)
    db.add(restaurant)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create closure.",
        ) from exc

    await db.refresh(closure)
    return closure


# DELETE /{restaurant_id}/closure
# Reopen the restaurant (remove the active closure)


@router.delete(
    "/{restaurant_id}/closure",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reopen a temporarily closed restaurant",
    description=(
        "Removes the active closure event and marks the restaurant as open. "
        "Returns 404 if there is no active closure."
    ),
)
async def delete_closure(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    restaurant = await _get_owned_restaurant(restaurant_id, current_user.id, db)

    now = datetime.now(UTC)
    active_closure = await db.scalar(
        select(RestaurantClosure).where(
            RestaurantClosure.restaurant_id == restaurant_id,
            RestaurantClosure.starts_at <= now,
            (RestaurantClosure.ends_at.is_(None)) | (RestaurantClosure.ends_at > now),
        )
    )

    if not active_closure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active closure found for this restaurant.",
        )

    await db.delete(active_closure)

    restaurant.is_manually_closed = False
    db.add(restaurant)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove closure.",
        ) from exc
