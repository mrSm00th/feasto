import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.reviews.schemas import ReviewListResponseSchema, SubmitReviewSchema
from app.modules.reviews.services import submit_review
from app.modules.users.models import User, UserRole

# Authenticated- review submission
router = APIRouter(prefix="/orders/{order_id}/review", tags=["reviews"])

# Authenticated- "my reviews"
my_reviews_router = APIRouter(prefix="/reviews/me", tags=["reviews"])

# Public restaurant reviews — no auth required, shown on browse/detail pages
public_router = APIRouter(prefix="/restaurants", tags=["reviews"])


@router.post(
    "",
    response_model=ReviewListResponseSchema.__fields__["reviews"].annotation.__args__[
        0
    ],
    status_code=201,
)
async def submit_order_review(
    order_id: uuid.UUID,
    data: SubmitReviewSchema,
    current_user: Annotated[
        User, Depends(require_roles(UserRole.CUSTOMER, UserRole.RIDER))
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Submit a review for a completed order.

    Customers can review riders or restaurants, while riders can review customers.
    """
    return await submit_review(
        order_id, current_user, data.reviewee_type, data.rating, data.comment, db
    )
