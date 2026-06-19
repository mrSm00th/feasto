import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.notifications.models import NotificationType
from app.modules.notifications.services import create_notification
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.orders.schemas import (
    AcceptOrderSchema,
    IncomingOrdersResponseSchema,
    OrderResponseSchema,
    RejectOrderSchema,
)
from app.modules.orders.services import get_order_owned_by_restaurant
from app.modules.orders.tasks import check_rider_assignment_timeout
from app.modules.restaurants.services import get_restaurant_owned_by
from app.modules.riders.services import dispatch_order_to_riders
from app.modules.users.models import User, UserRole

logger = logging.getLogger(__name__)


""""
    Handles the restaurant facing routes related to the orders
"""

restaurant_orders_router = APIRouter(prefix="/restaurants", tags=["restaurant-orders"])
order_actions_router = APIRouter(
    prefix="/restaurant/orders", tags=["restaurant-orders"]
)


@restaurant_orders_router.get(
    "/{restaurant_id}/orders",
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
        .where(Order.restaurant_id == restaurant_id, Order.status == OrderStatus.PLACED)
        .order_by(Order.created_at.asc())  # oldest orders first
    )

    orders = result.scalars().all()

    return IncomingOrdersResponseSchema(total=len(orders), orders=orders)


@order_actions_router.post(
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


@order_actions_router.post("/{order_id}/reject", response_model=OrderResponseSchema)
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


@order_actions_router.post(
    "/{order_id}/preparing",
    response_model=OrderResponseSchema,
)
async def change_order_status_to_preparing(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await get_order_owned_by_restaurant(order_id, current_user.id, db)

    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(
            status_code=409,
            detail="Order must be CONFIRMED before moving to PREPARING",
        )

    order.status = OrderStatus.PREPARING
    order.preparing_at = datetime.now(UTC)

    await create_notification(
        user_id=order.user_id,
        type=NotificationType.ORDER_PREPARING,
        reference_id=order.id,
        title="Preparation Started",
        content="The restaurant has started preparing your order",
        db=db,
    )

    await db.commit()
    await db.refresh(order)
    return order


@order_actions_router.post(
    "/{order_id}/ready-for-pickup",
    response_model=OrderResponseSchema,
)
async def change_order_status_to_ready_for_pickup(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.RESTAURANT_OWNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await get_order_owned_by_restaurant(order_id, current_user.id, db)

    if order.status != OrderStatus.PREPARING:
        raise HTTPException(
            status_code=409,
            detail="Order must be PREPARING before moving to READY_FOR_PICKUP",
        )

    order.status = OrderStatus.READY_FOR_PICKUP
    order.ready_at = datetime.now(UTC)

    await create_notification(
        user_id=order.user_id,
        type=NotificationType.ORDER_READY_FOR_PICKUP,
        reference_id=order.id,
        title="Order Ready for Pickup",
        content="Your order is ready and waiting for a rider",
        db=db,
    )

    await db.commit()
    await db.refresh(order)

    # Both of these happen AFTER commit — the order's READY_FOR_PICKUP
    # status is safely stored regardless the below operations

    # 1. Schedule the safety net first — before dispatch attempt.
    check_rider_assignment_timeout.apply_async(
        args=[str(order.id)],
        countdown=settings.rider_assignment_timeout_minutes * 60,
    )

    # 2. Attempt immediate dispatch — notify nearby riders right now.
    #    Runs after the timeout is scheduled so the safety net is always
    #    in place, regardless of how dispatch goes.
    try:
        riders_found = await dispatch_order_to_riders(order, db)

        if not riders_found:
            logger.warning(
                "No riders available for order %s — order will remain at "
                "READY_FOR_PICKUP until a rider comes online or the "
                "assignment timeout fires in %d minutes.",
                order.id,
                settings.rider_assignment_timeout_minutes,
            )

    except Exception:
        # just logging the dispatch failure as it's non-fatal — the restaurant's action succeeded,
        # the timeout task will handle cleanup if no rider ever comes.
        logger.exception(
            "Rider dispatch failed for order %s — order remains at "
            "READY_FOR_PICKUP, timeout task will handle cleanup.",
            order.id,
        )

    return order
