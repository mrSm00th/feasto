import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.reviews.schemas import (
    ReviewListResponseSchema,
    ReviewResponseSchema,
    SubmitReviewSchema,
)
from app.modules.reviews.services import (
    get_reviews_given_by_user,
    get_reviews_received_by_user,
    submit_review,
)
from app.modules.users.models import User, UserRole

# Authenticated- review submission
router = APIRouter(prefix="/orders/{order_id}/review", tags=["reviews"])

# Authenticated- "my reviews"
my_reviews_router = APIRouter(prefix="/reviews/me", tags=["reviews"])

# Public restaurant reviews — no auth required, shown on browse/detail pages
public_router = APIRouter(prefix="/restaurants", tags=["reviews"])


@router.post(
    "",
    response_model=ReviewResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def submit_order_review(
    order_id: uuid.UUID,
    data: SubmitReviewSchema,
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RIDER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await submit_review(
        order_id, current_user, data.reviewee_type, data.rating, data.comment, db
    )


@my_reviews_router.get(
    "/received",
    response_model=ReviewListResponseSchema,
)
async def get_my_received_reviews(
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RIDER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Reviews left ABOUT the current user — e.g. a rider's own rating history."""
    reviews, total = await get_reviews_received_by_user(
        current_user.id, db, skip, limit
    )
    return ReviewListResponseSchema(total=total, reviews=reviews)


@my_reviews_router.get(
    "/given",
    response_model=ReviewListResponseSchema,
)
async def get_my_given_reviews(
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RIDER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Reviews given by the current user"""
    reviews, total = await get_reviews_given_by_user(current_user.id, db, skip, limit)
    return ReviewListResponseSchema(total=total, reviews=reviews)
