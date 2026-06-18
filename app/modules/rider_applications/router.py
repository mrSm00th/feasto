import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.rider_applications.models import (
    IdentityProofType,
    VehicleType,
)
from app.modules.rider_applications.schemas import (
    IncomingRiderApplicationsResponseSchema,
    RiderApplicationResponseSchema,
    StartApplicationSchema,
)
from app.modules.rider_applications.services import (
    add_identity_proof,
    add_profile_image,
    add_vehicle_details,
    get_active_application_for_user,
    get_application_owned_by_user,
    start_application,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/rider-applications", tags=["rider-applications"])
admin_router = APIRouter(
    prefix="/admin/rider-applications", tags=["admin-rider-applications"]
)


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
    return await start_application(current_user, data.city, db)


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
    return application


@router.post(
    "/{application_id}/identity-proof", response_model=RiderApplicationResponseSchema
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
    return await add_identity_proof(
        application, identity_proof_type, identity_proof_number, image, db
    )


@router.post(
    "/{application_id}/profile-image", response_model=RiderApplicationResponseSchema
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
    return await add_profile_image(application, image, db)


@router.post(
    "/{application_id}/vehicle-details", response_model=RiderApplicationResponseSchema
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
    return await add_vehicle_details(
        application,
        vehicle_type,
        vehicle_number,
        license_number,
        license_expiry_date,
        license_image,
        db,
    )
