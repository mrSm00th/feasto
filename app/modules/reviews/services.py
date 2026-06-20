# reviews/service.py

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import Order, OrderStatus
from app.modules.restaurants.models import Restaurant
from app.modules.reviews.models import Review, RevieweeType, ReviewerRole
from app.modules.riders.models import Rider
from app.modules.users.models import User, UserRole


async def submit_review(
    order_id: uuid.UUID,
    reviewer: User,
    reviewee_type: RevieweeType,
    rating: int,
    comment: str | None,
    db: AsyncSession,
) -> Review:
    """
    Create a review for an order.

    Reviews can only be submitted after the order is delivered.
    """

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can only review delivered orders",
        )

    reviewee_user_id: uuid.UUID | None = None
    reviewee_restaurant_id: uuid.UUID | None = None
    rider: Rider | None = None
    restaurant: Restaurant | None = None

    if reviewer.role == UserRole.CUSTOMER:
        if order.user_id != reviewer.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your order"
            )

        if reviewee_type == RevieweeType.RIDER:
            if not order.rider_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No rider was assigned to this order",
                )
            rider = await db.get(Rider, order.rider_id)
            if not rider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Rider not found"
                )
            reviewee_user_id = rider.user_id

        elif reviewee_type == RevieweeType.RESTAURANT:
            restaurant = await db.get(Restaurant, order.restaurant_id)
            if not restaurant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found"
                )
            reviewee_restaurant_id = restaurant.id

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customers can only review riders or restaurants",
            )

        reviewer_role = ReviewerRole.CUSTOMER

    elif reviewer.role == UserRole.RIDER:
        if reviewee_type != RevieweeType.CUSTOMER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Riders can only review customers",
            )

        rider_result = await db.execute(
            select(Rider).where(Rider.user_id == reviewer.id)
        )
        rider_self = rider_result.scalar_one_or_none()

        if not rider_self or order.rider_id != rider_self.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your delivery"
            )

        reviewee_user_id = order.user_id
        reviewer_role = ReviewerRole.RIDER

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customers and riders can leave reviews",
        )

    existing = await db.execute(
        select(Review).where(
            Review.order_id == order_id,
            Review.reviewer_id == reviewer.id,
            Review.reviewee_type == reviewee_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted this review",
        )

    review = Review(
        order_id=order_id,
        reviewer_id=reviewer.id,
        reviewer_role=reviewer_role,
        reviewee_type=reviewee_type,
        reviewee_user_id=reviewee_user_id,
        reviewee_restaurant_id=reviewee_restaurant_id,
        rating=rating,
        comment=comment,
    )
    db.add(review)

    # formula:
    # new_avg = ((old_avg * old_count) + new_rating) / new_count

    if reviewee_type == RevieweeType.RIDER and rider:
        new_total = rider.total_reviews + 1
        rider.avg_rating = round(
            ((rider.avg_rating * rider.total_reviews) + Decimal(rating)) / new_total, 2
        )
        rider.total_reviews = new_total

    elif reviewee_type == RevieweeType.RESTAURANT and restaurant:
        new_total = restaurant.total_reviews + 1
        restaurant.avg_rating = round(
            ((restaurant.avg_rating * restaurant.total_reviews) + Decimal(rating))
            / new_total,
            2,
        )
        restaurant.total_reviews = new_total

    await db.commit()
    await db.refresh(review)
    return review
