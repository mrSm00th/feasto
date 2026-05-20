import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.admin.schemas import PartnerApplicationDetailed
from app.modules.partner_applications.models import (
    ApplicationStatus,
    PartnerApplication,
)
from app.modules.partner_applications.schemas import (
    PaginatedPartnerAppResponse,
    PartnerApplicationCreate,
    PartnerApplicationMini,
    PartnerApplicationResponse,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/api/partner-applications", tags=["partner applications"])


@router.post(
    "/",
    response_model=PartnerApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_partner_application(
    data: PartnerApplicationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
):

    result = await db.execute(
        select(PartnerApplication).where(
            PartnerApplication.applicant_id == current_user.id,
            PartnerApplication.status == ApplicationStatus.PENDING,
        )
    )

    existing_application = result.scalars().first()

    if existing_application:
        raise HTTPException(
            status_code=400, detail="You already have a pending application"
        )

    new_application = PartnerApplication(
        applicant_id=current_user.id,
        fssai_license_number=data.fssai_license_number,
        gst_number=data.gst_number,
    )

    try:
        db.add(new_application)
        await db.commit()
        await db.refresh(new_application)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Something went wrong while creating the application",
        )

    return new_application


# get all the user applications
@router.get(
    "/",
    response_model=PaginatedPartnerAppResponse,
)
async def get_partner_applications_paginated(
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.application_per_page,
):

    result_count = await db.execute(
        select(func.count())
        .select_from(PartnerApplication)
        .where(PartnerApplication.applicant_id == current_user.id)
    )

    total = result_count.scalar() or 0

    result = await db.execute(
        select(PartnerApplication)
        .where(PartnerApplication.applicant_id == current_user.id)
        .order_by(PartnerApplication.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    applications = result.scalars().all()

    has_more = skip + len(applications) < total

    return PaginatedPartnerAppResponse(
        applications=[
            PartnerApplicationMini.model_validate(application)
            for application in applications
        ],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# get the particular apllication of the owner by app_id
@router.get(
    "/{id}",
    response_model=PartnerApplicationDetailed,
)
async def get_owner_application_by_id(
    id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
):

    result = await db.execute(
        select(PartnerApplication).where(PartnerApplication.id == id)
    )

    application = result.scalars().first()

    if not application:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if application.applicant_id != current_user.id:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this application",
        )

    return application
