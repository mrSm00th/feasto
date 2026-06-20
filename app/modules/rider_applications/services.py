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
from app.core.storage import get_private_storage, get_public_storage
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
    city_name: str,
    db: AsyncSession,
) -> RiderApplication:
    existing = await get_active_application_for_user(user.id, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have an application in progress",
        )

    result = await db.execute(
        select(City).where(City.name == city_name, City.status == CityStatus.ACTIVE)
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


from app.core.image_processing import (
    ImageProcessingError,
    _image_key,
    process_thumbnail,
)


async def add_profile_image(
    application: RiderApplication,
    image: UploadFile,
    db: AsyncSession,
) -> RiderApplication:
    if application.status not in (
        RiderApplicationStatus.IDENTITY_PROOF_ADDED,
        RiderApplicationStatus.PROFILE_IMAGE_ADDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete identity proof before adding a profile photo",
        )

    try:
        content = await image.read()

        processed_bytes, filename = process_thumbnail(content)

    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    storage = get_private_storage()

    key = _image_key(
        application.id,
        filename,
        "rider-applications/profile-photos",
    )

    await storage.upload(
        processed_bytes,
        key,
        content_type="image/jpeg",
    )

    application.profile_image = key
    application.status = RiderApplicationStatus.PROFILE_IMAGE_ADDED

    await db.commit()
    await db.refresh(application)

    return application


from app.core.image_processing import ImageProcessingError, process_document


async def add_vehicle_details(
    application: RiderApplication,
    vehicle_type: VehicleType,
    vehicle_number: str,
    license_number: str,
    license_expiry_date,
    license_image: UploadFile,
    db: AsyncSession,
) -> RiderApplication:
    if application.status not in (
        RiderApplicationStatus.PROFILE_IMAGE_ADDED,
        RiderApplicationStatus.VEHICLE_DETAILS_ADDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the profile photo step before adding vehicle details",
        )

    try:
        content = await license_image.read()

        processed_bytes, filename = process_document(content)

    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    storage = get_private_storage()

    key = f"rider-applications/licenses/" f"{application.id}/{filename}"

    await storage.upload(
        processed_bytes,
        key,
        content_type="image/jpeg",
    )

    application.vehicle_type = vehicle_type
    application.vehicle_number = vehicle_number
    application.license_number = encrypt_pii(license_number)
    application.license_expiry_date = license_expiry_date
    application.license_image = key
    application.status = RiderApplicationStatus.VEHICLE_DETAILS_ADDED

    await db.commit()
    await db.refresh(application)

    return application


async def submit_for_review(
    application: RiderApplication,
    db: AsyncSession,
) -> RiderApplication:
    if application.status != RiderApplicationStatus.VEHICLE_DETAILS_ADDED:
        raise HTTPException(
            status_code=409,
            detail="All steps must be completed before submitting for review",
        )

    application.status = RiderApplicationStatus.PENDING_REVIEW
    application.submitted_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(application)
    return application


async def approve_rider_application(
    application: RiderApplication,
    admin: User,
    db: AsyncSession,
) -> RiderApplication:
    """
    Owns the entire approval transaction: flips application status,
    promotes the user's role, creates the operational Rider profile,
    and moves the profile photo from the private bucket into the
    public bucket so it can be shown to customers tracking a delivery.
    """
    from app.modules.riders.models import (
        Rider,
    )  # local import — avoids circular dependency

    if application.status != RiderApplicationStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="Application is not pending review")

    # Move profile photo: private (onboarding) → public (operational)
    private_storage = get_private_storage()
    public_storage = get_public_storage()

    public_key = f"riders/{application.applicant_id}/profile.jpg"

    try:
        signed_url = await private_storage.generate_signed_url(
            application.profile_image, expires_in=60
        )
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(signed_url)
            response.raise_for_status()
            image_bytes = response.content

        await public_storage.upload(image_bytes, public_key, content_type="image/jpeg")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            # detail="Failed to finalize rider profile photo. Please try approving again.",
            detail=str(exc),
        )

    application.status = RiderApplicationStatus.APPROVED
    application.reviewed_by = admin.id
    application.reviewed_at = datetime.now(UTC)

    application.applicant.role = UserRole.RIDER

    rider = Rider(
        user_id=application.applicant_id,
        vehicle_type=application.vehicle_type,
        vehicle_number=application.vehicle_number,
        license_expiry_date=application.license_expiry_date,
        profile_image=public_key,
    )
    db.add(rider)

    await db.commit()
    await db.refresh(application)
    return application


async def reject_rider_application(
    application: RiderApplication,
    admin: User,
    reason: str,
    db: AsyncSession,
) -> RiderApplication:
    if application.status != RiderApplicationStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="Application is not pending review")

    application.status = RiderApplicationStatus.REJECTED
    application.reviewed_by = admin.id
    application.reviewed_at = datetime.now(UTC)
    application.rejection_reason = reason

    await db.commit()
    await db.refresh(application)
    return application
