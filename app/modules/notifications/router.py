import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import (
    NotificationDetailResponse,
    NotificationResponse,
    PaginatedNotifications,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "/me",
    response_model=PaginatedNotifications,
)
async def get_user_notifications(
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.notifications_per_page,
):

    result = await db.execute(select(User).where(User.id == current_user.id))

    existing_user = result.scalars().first()

    if not existing_user:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    result_count = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
        )
    )

    total = result_count.scalar() or 0

    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(
            Notification.is_read.asc(),
            Notification.created_at.desc(),
        )
        .offset(skip)
        .limit(limit)
    )

    notifications = result.scalars().all()

    has_more = skip + len(notifications) < total

    return PaginatedNotifications(
        notifications=[
            NotificationResponse.model_validate(notification)
            for notification in notifications
        ],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get(
    "/{notification_id}",
    response_model=NotificationDetailResponse,
)
async def get_notification_by_id(
    notification_id: uuid.UUID,
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )

    notification = result.scalars().first()

    if not notification:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return_object = NotificationDetailResponse(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        content=notification.content,
        is_read=notification.is_read,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )

    return return_object


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )

    notification = result.scalars().first()

    if not notification:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = True
    notification.read_at = datetime.now(UTC)

    try:
        await db.commit()

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read",
        )


@router.patch(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_all_notification_as_read(
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RESTAURANT_OWNER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
        .values(
            is_read=True,
            read_at=datetime.now(UTC),
        )
    )

    try:
        await db.commit()

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark all notification as read",
        )
