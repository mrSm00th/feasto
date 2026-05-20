import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.modules.users.models as models
from app.core.auth import hash_password
from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.admin.schemas import (
    PaginatedApplicationResponse,
    PartnerApplicationAdminReview,
    PartnerApplicationDetailed,
    PendingApplicationsList,
)
from app.modules.partner_applications.models import (
    ApplicationStatus,
    PartnerApplication,
)
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserCreate, UserPrivate

router = APIRouter(prefix="/api/admin", tags=["admins"])


@router.post(
    "/",
    response_model=UserPrivate,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin(
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.full_name) == user.full_name.lower()
        )
    )

    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this full name already exists",
        )

    result = await db.execute(
        select(models.User).where(models.User.email == user.email)
    )

    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    result = await db.execute(
        select(models.User).where(models.User.phone_number == user.phone_number)
    )

    existing_phone_number = result.scalars().first()

    if existing_phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this phone number already exists",
        )

    new_user = models.User(
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        password_hash=hash_password(user.password),
        role=UserRole.ADMIN,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.get(
    "/owner-applications",
    response_model=PaginatedApplicationResponse,
    status_code=status.HTTP_200_OK,
)
async def paginated_pending_applications(
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.application_per_page,
):
    result_count = await db.execute(
        select(func.count())
        .select_from(PartnerApplication)
        .where(PartnerApplication.status == ApplicationStatus.PENDING)
    )

    total = result_count.scalar() or 0

    result = await db.execute(
        select(PartnerApplication)
        .options(selectinload(PartnerApplication.applicant))
        .where(PartnerApplication.status == ApplicationStatus.PENDING)
        .order_by(PartnerApplication.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    applications = result.scalars().all()

    has_more = skip + len(applications) < total

    return PaginatedApplicationResponse(
        applications=[
            PendingApplicationsList.model_validate(application)
            for application in applications
        ],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


# route for all pending applications
@router.get(
    "/owner-applications/{id}",
    response_model=PartnerApplicationDetailed,
    status_code=status.HTTP_200_OK,
)
async def onwer_application_detailed(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(PartnerApplication)
        .options(selectinload(PartnerApplication.applicant))
        .where(PartnerApplication.id == id)
    )

    application = result.scalars().first()

    return application


@router.patch(
    "/owner-applications/{id}/review",
    response_model=PartnerApplicationAdminReview,
)
async def review_owner_application(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    approve: bool,
    rejection_reason: Annotated[str | None, Query(max_length=500)] = None,
):

    result = await db.execute(
        select(PartnerApplication)
        .options(selectinload(PartnerApplication.applicant))
        .where(PartnerApplication.id == id)
    )

    application = result.scalars().first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if application.status != ApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending applications can be reviewed",
        )

    if approve:
        application.status = ApplicationStatus.APPROVED
        application.applicant.role = UserRole.RESTAURANT_OWNER
    else:
        application.status = ApplicationStatus.REJECTED

        if rejection_reason:
            application.rejection_reason = rejection_reason

    application.reviewed_by = current_user.id
    application.reviewed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(application)

    return application
