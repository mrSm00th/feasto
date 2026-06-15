import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.orders.schemas import (
    AcceptOrderSchema,
    IncomingOrdersResponseSchema,
    OrderResponseSchema,
    RejectOrderSchema,
)
from app.modules.orders.services import (
    create_notification,
    get_order_owned_by_restaurant,
    get_restaurant_owned_by,
)
from app.modules.restaurants.models import Restaurant
from app.modules.users.models import Notification, NotificationType, User, UserRole

# restaurant-facing routes

router = APIRouter(prefix="/restaurant/orders", tags=["restaurant-orders"])


@router.get(
    "",
    response_model=IncomingOrdersResponseSchema,
)
async def get_incoming_orders_for_restaurant(
    restaurant_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    # validate this restaurant belongs to the current user

    await get_restaurant_owned_by(restaurant_id, current_user.id, db)

    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(Order.restaurant_id == restaurant_id)
        .order_by(Order.created_at.desc())  # oldest orders first
    )

    orders = result.scalars().all()

    return IncomingOrdersResponseSchema(total=len(orders), orders=orders)


@router.post(
    "/{order_id}/accept",
    response_model=OrderResponseSchema,
)
async def accept_order(
    order_id: uuid.UUID,
    data: AcceptOrderSchema,  # { estimated_prep_minutes: int }
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await get_order_owned_by_restaurant(order_id, current_user.id, db)

    if order.status != OrderStatus.PLACED:
        raise HTTPException(
            status_code=409, detail="Order cannot be accepted in its current state"
        )

    now = datetime.now(UTC)
    order.status = OrderStatus.CONFIRMED
    order.confirmed_at = now
    order.estimated_ready_at = now + timedelta(minutes=data.estimated_prep_minutes)

    await create_notification(
        user_id=order.user_id,
        type=NotificationType.ORDER_CONFIRMED,
        reference_id=order.id,
        title="Order Confirmed!",
        content=f"Your order will be ready in {data.estimated_prep_minutes} minutes",
        db=db,
    )

    await db.commit()
    await db.refresh(order)
    return order


@router.post("/{order_id}/reject", response_model=OrderResponseSchema)
async def reject_order(
    order_id: uuid.UUID,
    data: RejectOrderSchema,  # { reason: str }
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await get_order_owned_by_restaurant(order_id, current_user.id, db)

    if order.status != OrderStatus.PLACED:
        raise HTTPException(
            status_code=409, detail="Order cannot be rejected in its current state"
        )

    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = CancellationReason.RESTAURANT_REJECTED
    order.cancellation_note = data.reason
    order.cancelled_at = datetime.now(UTC)

    await create_notification(
        user_id=order.user_id,
        type=NotificationType.ORDER_REJECTED,
        reference_id=order.id,
        title="Order Rejected",
        content=f"The restaurant couldn't accept your order: {data.reason}",
        db=db,
    )

    # TODO: trigger refund (Phase 6 — refund integration)

    await db.commit()
    await db.refresh(order)
    return order
