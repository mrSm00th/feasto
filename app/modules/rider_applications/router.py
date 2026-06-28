import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.core.encryption import decrypt_pii
from app.core.storage import get_private_storage
from app.db.database import get_db
from app.modules.rider_applications.models import (
    IdentityProofType,
    RiderApplication,
    RiderApplicationStatus,
    VehicleType,
)
from app.modules.rider_applications.schemas import (
    IncomingRiderApplicationsResponseSchema,
    RejectApplicationSchema,
    RiderApplicationAdminDetailSchema,
    RiderApplicationResponseSchema,
    StartApplicationSchema,
)
from app.modules.rider_applications.services import (
    add_identity_proof,
    add_profile_image,
    add_vehicle_details,
    approve_rider_application,
    get_active_application_for_user,
    get_application_owned_by_user,
    reject_rider_application,
    start_application,
    submit_for_review,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/rider-applications", tags=["rider-applications"])
admin_router = APIRouter(
    prefix="/admin/rider-applications", tags=["admin-rider-applications"]
)

# helper


async def resolve_application_urls(
    application: RiderApplication,
) -> RiderApplicationResponseSchema:
    storage = get_private_storage()
    data = RiderApplicationResponseSchema.model_validate(application).model_dump()

    for field in ("identity_proof_image", "profile_image", "license_image"):
        raw_key = getattr(application, field)
        data[field] = await storage.generate_signed_url(raw_key) if raw_key else None

    return RiderApplicationResponseSchema(**data)


#  rider-facing routes


@router.post(
    "",
    response_model=RiderApplicationResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_rider_application(
    data: StartApplicationSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # no file fields at this stage — safe to return directly
    application = await start_application(current_user, data.city_name, db)
    return application


@router.get(
    "/me",
    response_model=RiderApplicationResponseSchema,
)
async def get_my_application(
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await get_active_application_for_user(current_user.id, db)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active application found",
        )
    return await resolve_application_urls(application)


@router.post(
    "/{application_id}/identity-proof",
    response_model=RiderApplicationResponseSchema,
)
async def submit_identity_proof(
    application_id: uuid.UUID,
    identity_proof_type: Annotated[IdentityProofType, Form()],
    identity_proof_number: Annotated[str, Form()],
    image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await get_application_owned_by_user(
        application_id, current_user.id, db
    )
    application = await add_identity_proof(
        application, identity_proof_type, identity_proof_number, image, db
    )
    return await resolve_application_urls(application)


@router.post(
    "/{application_id}/profile-image",
    response_model=RiderApplicationResponseSchema,
)
async def submit_profile_image(
    application_id: uuid.UUID,
    image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await get_application_owned_by_user(
        application_id, current_user.id, db
    )
    application = await add_profile_image(application, image, db)
    return await resolve_application_urls(application)


@router.post(
    "/{application_id}/vehicle-details",
    response_model=RiderApplicationResponseSchema,
)
async def submit_vehicle_details(
    application_id: uuid.UUID,
    vehicle_type: Annotated[VehicleType, Form()],
    vehicle_number: Annotated[str, Form()],
    license_number: Annotated[str, Form()],
    license_expiry_date: Annotated[date, Form()],
    license_image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if license_expiry_date <= date.today():
        raise HTTPException(status_code=400, detail="License has expired")

    application = await get_application_owned_by_user(
        application_id, current_user.id, db
    )
    application = await add_vehicle_details(
        application,
        vehicle_type,
        vehicle_number,
        license_number,
        license_expiry_date,
        license_image,
        db,
    )
    return await resolve_application_urls(application)


@router.post(
    "/{application_id}/submit",
    response_model=RiderApplicationResponseSchema,
)
async def submit_application_for_review(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await get_application_owned_by_user(
        application_id, current_user.id, db
    )
    application = await submit_for_review(application, db)

    return await resolve_application_urls(application)


# admin-facing routes


@admin_router.get(
    "",
    response_model=IncomingRiderApplicationsResponseSchema,
)
async def list_pending_applications(
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(RiderApplication)
        .where(RiderApplication.status == RiderApplicationStatus.PENDING_REVIEW)
        .order_by(RiderApplication.submitted_at.asc())
    )
    applications = result.scalars().all()

    # resolve URLs for each application in the list
    resolved = []
    for application in applications:
        resolved.append(await resolve_application_urls(application))

    return IncomingRiderApplicationsResponseSchema(
        total=len(resolved),
        applications=resolved,
    )


@admin_router.get(
    "/{application_id}",
    response_model=RiderApplicationAdminDetailSchema,
)
async def get_application_detail(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await db.get(RiderApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    storage = get_private_storage()

    # admin gets decrypted PII + presigned URLs for all three documents
    return RiderApplicationAdminDetailSchema(
        **RiderApplicationResponseSchema.model_validate(application).model_dump(),
        identity_proof_number=decrypt_pii(application.identity_proof_number),
        license_number=decrypt_pii(application.license_number),
        identity_proof_image_url=await storage.generate_signed_url(
            application.identity_proof_image
        ),
        profile_image_url=await storage.generate_signed_url(application.profile_image),
        license_image_url=await storage.generate_signed_url(application.license_image),
    )


@admin_router.post(
    "/{application_id}/approve",
    response_model=RiderApplicationResponseSchema,
)
async def approve_application(
    application_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await db.get(RiderApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    application = await approve_rider_application(application, current_user, db)
    return await resolve_application_urls(application)


@admin_router.post(
    "/{application_id}/reject",
    response_model=RiderApplicationResponseSchema,
)
async def reject_application(
    application_id: uuid.UUID,
    data: RejectApplicationSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    application = await db.get(RiderApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    application = await reject_rider_application(
        application, current_user, data.reason, db
    )
    return await resolve_application_urls(application)
