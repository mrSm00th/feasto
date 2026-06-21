import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.modules.users.models as models
from app.core.auth import hash_password
from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.admins.schemas import (
    ApprovedCuisineResponse,
    PaginatedApplicationResponse,
    PaginatedPendingCuisineResponse,
    PartnerApplicationAdminReview,
    PartnerApplicationWithHistory,
    PendingApplicationsList,
    PendingCuisineRequest,
    PendingCuisineRequestDetail,
    RejectionReason,
    RevocationReason,
)
from app.modules.notifications.models import Notification, NotificationType
from app.modules.partner_applications.models import (
    ApplicationStatus,
    PartnerApplication,
)
from app.modules.restaurants.models import (
    CuisineRequest,
    CuisineRequestHistory,
    CuisineStatus,
    CuisineType,
    MappedCuisineStatus,
    Restaurant,
    RestaurantCuisineMapping,
)
from app.modules.users.models import User, UserRole
from app.modules.users.schemas import UserCreate, UserPrivate

router = APIRouter(prefix="/admins", tags=["admins"])


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
    response_model=PartnerApplicationWithHistory,
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

    if not application:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    history_result = await db.execute(
        select(PartnerApplication)
        .where(
            PartnerApplication.applicant_id == application.applicant_id,
            PartnerApplication.id != application.id,
            PartnerApplication.status == ApplicationStatus.REJECTED,
        )
        .order_by(PartnerApplication.created_at.desc())
        .limit(5)
    )

    history = history_result.scalars().all()

    return PartnerApplicationWithHistory(
        application=application,
        history=history,
    )


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


@router.get(
    "/cuisines/pending",
    response_model=PaginatedPendingCuisineResponse,
)
async def paginated_pending_cuisine_requests(
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.application_per_page,
):

    result_count = await db.execute(
        select(func.count()).select_from(CuisineRequest),
    )

    total = result_count.scalar() or 0

    result = await db.execute(
        select(CuisineRequest)
        .order_by(CuisineRequest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    pending_cuisines = result.scalars().all()

    has_more = skip + len(pending_cuisines) < total

    return PaginatedPendingCuisineResponse(
        cuisines=[
            PendingCuisineRequest.model_validate(pending_cuisine)
            for pending_cuisine in pending_cuisines
        ],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get(
    "/cuisines/{id}/pending",
    response_model=PendingCuisineRequestDetail,
)
async def pending_cuisine_detailed_view(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CuisineRequest).where(CuisineRequest.id == id))
    pending_cuisine = result.scalar_one_or_none()

    if not pending_cuisine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine request not found",
        )

    similar_approved_cuisines = []
    similar_pending_cuisines = []

    search_terms = [
        word for word in pending_cuisine.cuisine_name.split() if len(word) > 3
    ]

    if search_terms:
        # Similar approved cuisines
        result = await db.execute(
            select(CuisineType)
            .where(
                CuisineType.status == CuisineStatus.ACTIVE,
                or_(
                    *[
                        CuisineType.cuisine_name.ilike(f"%{word}%")
                        for word in search_terms
                    ]
                ),
            )
            .limit(10)
        )

        similar_approved_cuisines = result.scalars().all()

        # Similar pending requests
        result = await db.execute(
            select(CuisineRequest)
            .where(
                CuisineRequest.id != pending_cuisine.id,
                or_(
                    *[
                        CuisineRequest.cuisine_name.ilike(f"%{word}%")
                        for word in search_terms
                    ]
                ),
            )
            .limit(10)
        )

        similar_pending_cuisines = result.scalars().all()

    result = await db.execute(
        select(func.count())
        .select_from(RestaurantCuisineMapping)
        .where(RestaurantCuisineMapping.request_id == pending_cuisine.id)
    )

    request_count = result.scalar() or 0

    return {
        "id": pending_cuisine.id,
        "requested_by": pending_cuisine.requested_by,
        "cuisine_name": pending_cuisine.cuisine_name,
        "cuisine_slug": pending_cuisine.cuisine_slug,
        "created_at": pending_cuisine.created_at,
        "request_count": request_count,
        "similar_approved_cuisines": similar_approved_cuisines,
        "similar_pending_cuisines": similar_pending_cuisines,
    }


@router.post(
    "/cuisines/{id}/approve",
    response_model=ApprovedCuisineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def approve_pending_cuisine(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(select(CuisineRequest).where(CuisineRequest.id == id))

    pending_cuisine = result.scalars().first()

    if not pending_cuisine:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine request not found",
        )

    # server side safety check for existing cuisine

    result = await db.execute(
        select(CuisineType).where(
            CuisineType.cuisine_slug == pending_cuisine.cuisine_slug
        )
    )

    existing_cuisine = result.scalars().first()

    if existing_cuisine:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Cuisine '{existing_cuisine.cuisine_name}' " "already exists."),
        )

    try:
        new_cuisine = CuisineType(
            cuisine_name=pending_cuisine.cuisine_name,
            cuisine_slug=pending_cuisine.cuisine_slug,
            approved_by=current_user.id,
            approved_at=datetime.now(UTC),
            status=CuisineStatus.ACTIVE,
        )

        db.add(new_cuisine)
        await db.flush()

        results = await db.execute(
            select(User.id)
            .distinct()
            .join(Restaurant, Restaurant.owner_id == User.id)
            .join(
                RestaurantCuisineMapping,
                RestaurantCuisineMapping.restaurant_id == Restaurant.id,
            )
            .where(RestaurantCuisineMapping.request_id == pending_cuisine.id)
        )

        owner_ids = results.scalars().all()

        notifications = [
            Notification(
                user_id=owner_id,
                type=NotificationType.CUISINE_APPROVED,
                reference_id=new_cuisine.id,
                title="Cuisine Request Accepted",
                content=(
                    f"The cuisine '{pending_cuisine.cuisine_name}' "
                    f"was Accepted by an administrator."
                ),
            )
            for owner_id in owner_ids
        ]

        db.add_all(notifications)

        await db.execute(
            update(RestaurantCuisineMapping)
            .where(RestaurantCuisineMapping.request_id == pending_cuisine.id)
            .values(
                cuisine_id=new_cuisine.id,
                request_id=None,
                status=MappedCuisineStatus.ACTIVE,
            ),
        )

        await db.delete(pending_cuisine)

        await db.commit()

    except IntegrityError as exe:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cuisine approval failed due to a data conflict.",
        )

    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            # detail="Failed to approve cuisine request.",
            detail=str(exc),
        )

    await db.refresh(new_cuisine)

    return new_cuisine


@router.patch(
    "/cuisines/{id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_pending_cuisine(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: RejectionReason,
):

    result = await db.execute(select(CuisineRequest).where(CuisineRequest.id == id))

    pending_cuisine = result.scalars().first()

    if not pending_cuisine:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine request not found",
        )

    new_history = CuisineRequestHistory(
        requested_by=pending_cuisine.requested_by,
        cuisine_name=pending_cuisine.cuisine_name,
        cuisine_slug=pending_cuisine.cuisine_slug,
        rejected_by=current_user.id,
        rejection_reason=data.rejection_reason,
        created_at=pending_cuisine.created_at,
        rejected_at=datetime.now(UTC),
    )

    db.add(new_history)
    await db.flush()

    result = await db.execute(
        select(User.id)
        .distinct()
        .join(Restaurant, Restaurant.owner_id == User.id)
        .join(
            RestaurantCuisineMapping,
            RestaurantCuisineMapping.restaurant_id == Restaurant.id,
        )
        .where(RestaurantCuisineMapping.request_id == pending_cuisine.id)
    )

    owner_ids = result.scalars().all()

    notifications = [
        Notification(
            user_id=owner_id,
            type=NotificationType.CUISINE_REJECTED,
            reference_id=new_history.id,
            title="Cuisine Request Rejected",
            content=(
                f"The cuisine '{pending_cuisine.cuisine_name}' "
                f"was rejected by an administrator."
            ),
        )
        for owner_id in owner_ids
    ]

    db.add_all(notifications)

    await db.execute(
        delete(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.request_id == pending_cuisine.id
        )
    )

    try:

        await db.delete(pending_cuisine)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cuisine rejection failed due to a data conflict.",
        )

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject cuisine request.",
        )


@router.patch(
    "/cuisines/{id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_approved_cuisine(
    id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    data: RevocationReason,
):

    result = await db.execute(select(CuisineType).where(CuisineType.id == id))

    approved_cuisine = result.scalars().first()

    if not approved_cuisine:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuisine Not found",
        )

    approved_cuisine.status = CuisineStatus.REVOKED
    approved_cuisine.revocation_reason = data.revocation_reason
    approved_cuisine.revoked_at = datetime.now(UTC)
    approved_cuisine.revoked_by = current_user.id

    result = await db.execute(
        select(User.id)
        .distinct()
        .join(Restaurant, Restaurant.owner_id == User.id)
        .join(
            RestaurantCuisineMapping,
            RestaurantCuisineMapping.restaurant_id == Restaurant.id,
        )
        .where(RestaurantCuisineMapping.cuisine_id == approved_cuisine.id)
    )

    owner_ids = result.scalars().all()

    notifications = [
        Notification(
            user_id=owner_id,
            type=NotificationType.CUISINE_REVOKED,
            reference_id=approved_cuisine.id,
            title="Cuisine Request Revoked",
            content=(
                f"The cuisine '{approved_cuisine.cuisine_name}' used by your restaurant"
                f"was rejected by an administrator."
            ),
        )
        for owner_id in owner_ids
    ]

    db.add_all(notifications)

    await db.execute(
        delete(RestaurantCuisineMapping).where(
            RestaurantCuisineMapping.cuisine_id == approved_cuisine.id
        )
    )

    try:

        await db.delete(approved_cuisine)
        await db.commit()

    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            # detail="Cuisine revocation failed due to a data conflict.",
            detail=str(exc),
        )

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject cuisine request.",
        )
