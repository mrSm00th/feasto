import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_pii, encrypt_pii
from app.core.image_processing import (
    ImageProcessingError,
    process_document,
    process_thumbnail,
)
from app.core.storage import get_private_storage
from app.modules.locations.models import City, CityStatus
from app.modules.rider_applications.models import (
    IdentityProofType,
    RiderApplication,
    RiderApplicationStatus,
    VehicleType,
)
from app.modules.users.models import User, UserRole

MAX_UPLOAD_SIZE_BYTES = 8 * 1024 * 1024  # raw upload cap, before processing


async def _read_upload(image: UploadFile) -> bytes:
    """Reads raw bytes off the wire — format/dimension validation happens
    inside image_processing, not here. This just guards total payload size."""
    file_bytes = await image.read()

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File must be smaller than 8MB")

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
        raise HTTPException(status_code=404, detail="Application not found")

    return application


async def start_application(
    user: User,
    city_id: uuid.UUID,
    db: AsyncSession,
) -> RiderApplication:
    existing = await get_active_application_for_user(user.id, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an application in progress",
        )

    result = await db.execute(
        select(City).where(City.id == city_id, City.status == CityStatus.ACTIVE)
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


async def add_identity_proof(
    application: RiderApplication,
    proof_type: IdentityProofType,
    proof_number: str,
    image: UploadFile,
    db: AsyncSession,
) -> RiderApplication:
    if application.status not in (
        RiderApplicationStatus.CITY_ADDED,
        RiderApplicationStatus.IDENTITY_PROOF_ADDED,
    ):
        raise HTTPException(
            status_code=409,
            detail="Identity proof can only be added at this stage of the application",
        )

    raw_bytes = await _read_upload(image)

    try:
        processed_bytes, filename = process_document(raw_bytes)
    except ImageProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    storage = get_private_storage()
    key = f"rider-applications/{application.id}/identity-proof-{filename}"
    await storage.upload(processed_bytes, key, content_type="image/jpeg")

    application.identity_proof_type = proof_type
    application.identity_proof_number = encrypt_pii(proof_number)
    application.identity_proof_image = key
    application.status = RiderApplicationStatus.IDENTITY_PROOF_ADDED

    await db.commit()
    await db.refresh(application)
    return application
