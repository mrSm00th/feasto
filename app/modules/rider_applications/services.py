import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.locations.models import City, CityStatus
from app.modules.rider_applications.models import (
    RiderApplication,
    RiderApplicationStatus,
)
from app.modules.users.models import User, UserRole

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def read_and_validate_image(image: UploadFile) -> bytes:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG, or WEBP images are allowed"
        )

    file_bytes = await image.read()

    if len(file_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be smaller than 5MB",
        )

    return file_bytes


async def get_active_application_for_user(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> RiderApplication | None:
    result = await db.execute(
        select(RiderApplication).where(
            RiderApplication.applicant_id == user_id,
            RiderApplication.status.notin_(
                [RiderApplicationStatus.APPROVED, RiderApplicationStatus.REJECTED]
            ),
        )
    )
    return result.scalar_one_or_none()


async def get_application_owned_by_user(
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> RiderApplication:
    result = await db.execute(
        select(RiderApplication).where(
            RiderApplication.id == application_id,
            RiderApplication.applicant_id == user_id,
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    return application


async def start_application(
    user: User,
    city: str,
    db: AsyncSession,
) -> RiderApplication:
    existing = await get_active_application_for_user(user.id, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an application in progress",
        )

    city = city.strip().lower()

    result = await db.execute(
        select(City).where(
            City.name == city,
            City.status == CityStatus.ACTIVE,
        )
    )
    city = result.scalar_one_or_none()

    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We are not currently operating in this city",
        )

    application = RiderApplication(
        applicant_id=user.id,
        city_id=city.id,
        status=RiderApplicationStatus.CITY_ADDED,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application
