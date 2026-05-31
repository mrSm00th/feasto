import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.modules.users.models as models
from app.core.auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.restaurants.models import Restaurant
from app.modules.users.models import Notification, User, UserRole
from app.modules.users.schemas import (
    CuisineRequestHistroryResponse,
    NotificationDetailResponse,
    NotificationResponse,
    PaginatedNotifications,
    PaginatedOwnerRestaurant,
    RestaurantList,
    Token,
    UserCreate,
    UserPrivate,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post(
    "",
    response_model=UserPrivate,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
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
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    # NOTE: OAuth2 standard requires login credentials to be sent as form data, not JSON
    # username=alex&password=secret
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    result = await db.execute(
        select(models.User).where(models.User.email == form_data.username)
    )

    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=access_token_expires,
    )

    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user


@router.get(
    "/me/restaurants",
    response_model=PaginatedOwnerRestaurant,
)
async def get_current_user_restaurants(
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = settings.restaurants_per_page,
):

    result = await db.execute(
        select(func.count())
        .select_from(Restaurant)
        .where(Restaurant.owner_id == current_user.id)
    )

    total = result.scalar() or 0

    result = await db.execute(
        select(Restaurant)
        .options(selectinload(Restaurant.primary_image))
        .where(Restaurant.owner_id == current_user.id)
        .order_by(Restaurant.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    restaurants = result.scalars().all()

    has_more = skip + len(restaurants) < total

    return PaginatedOwnerRestaurant(
        restaurants=[
            RestaurantList.model_validate(restaurant) for restaurant in restaurants
        ],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )


@router.get(
    "/notifications",
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
    "/notifications/{notification_id}",
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
        select(Notification)
        .options(selectinload(Notification.reference))
        .where(
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
        reference=CuisineRequestHistroryResponse(
            id=notification.reference.id,
            cuisine_name=notification.reference.cuisine_name,
        ),
    )

    return return_object


@router.patch(
    "/notifications/{notification_id}/read",
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
    "/notifications/read-all",
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
