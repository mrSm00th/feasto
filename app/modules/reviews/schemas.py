# reviews/schemas.py

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.reviews.models import RevieweeType, ReviewerRole


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class SubmitReviewSchema(BaseSchema):
    reviewee_type: RevieweeType
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ReviewResponseSchema(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_role: ReviewerRole
    reviewee_type: RevieweeType
    reviewee_user_id: uuid.UUID | None
    reviewee_restaurant_id: uuid.UUID | None
    rating: int
    comment: str | None
    created_at: datetime


class ReviewListResponseSchema(BaseSchema):
    total: int
    reviews: list[ReviewResponseSchema]
