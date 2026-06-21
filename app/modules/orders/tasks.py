import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.modules.notifications.models import NotificationType
from app.modules.notifications.services import create_notification
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.payments.services import initiate_refund


@celery_app.task(name="orders.check_order_timeout")
def check_order_timeout(order_id_str: str) -> None:
    """
    Celery entry point must be sync.
    since our routes are async, we call the async func inside this sync func
    """
    asyncio.run(_check_order_timeout_async(order_id_str))


async def _check_order_timeout_async(order_id_str: str) -> None:
    order_id = uuid.UUID(order_id_str)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.payment))
            .where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()

        if not order:
            return

        # Nothing to do if the order already moved past these states —
        # as restaurant already responded, or payment already confirmed
        if order.status not in (OrderStatus.PLACED, OrderStatus.AWAITING_PAYMENT):
            return

        was_awaiting_payment = order.status == OrderStatus.AWAITING_PAYMENT

        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.now(UTC)

        if was_awaiting_payment:
            order.cancellation_reason = CancellationReason.PAYMENT_FAILED
            order.cancellation_note = "Payment was not completed in time"
            # no refund — nothing was ever captured
        else:
            order.cancellation_reason = CancellationReason.RESTAURANT_TIMEOUT
            order.cancellation_note = "Restaurant did not respond in time"

            await initiate_refund(
                order_id=order.id,
                reason="Order auto-cancelled: restaurant did not respond in time",
                db=db,
            )

        await create_notification(
            user_id=order.user_id,
            type=NotificationType.ORDER_CANCELLED,
            reference_id=order.id,
            title="Order Cancelled",
            content=(
                "Your payment session expired."
                if was_awaiting_payment
                else "The restaurant didn't respond in time. Your payment will be refunded."
            ),
            db=db,
        )

        await db.commit()


@celery_app.task(name="orders.check_rider_assignment_timeout")
def check_rider_assignment_timeout(order_id_str: str) -> None:
    """

    Runs N minutes after the order status is changed to READY_FOR_PICKUP.
    If no rider is assigned by then, worker auto cancels the order
    """
    asyncio.run(_check_rider_assignment_timeout_async(order_id_str))


async def _check_rider_assignment_timeout_async(order_id_str: str) -> None:
    order_id = uuid.UUID(order_id_str)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.payment))
            .where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()

        if not order:
            return

        # Rider was found and assigned in time — nothing to do
        if order.status != OrderStatus.READY_FOR_PICKUP:
            return

        # No rider found in time — cancel and refund
        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = CancellationReason.NO_RIDER_AVAILABLE
        order.cancellation_note = (
            "No rider available in the area. Your order has been cancelled."
        )
        order.cancelled_at = datetime.now(UTC)

        await initiate_refund(
            order_id=order.id,
            reason="Order auto-cancelled: no rider available",
            db=db,
        )

        await create_notification(
            user_id=order.user_id,
            type=NotificationType.ORDER_CANCELLED,
            reference_id=order.id,
            title="Order Cancelled — No Rider Available",
            content=(
                "We couldn't find a rider for your order. "
                "Your payment will be refunded shortly. We're sorry for the inconvenience."
            ),
            db=db,
        )

        # notifying restro- restaurant should know their prepared order was cancelled
        restaurant = await db.get(type(order.restaurant), order.restaurant_id)
        if restaurant:
            await create_notification(
                user_id=restaurant.owner_id,
                type=NotificationType.ORDER_CANCELLED,
                reference_id=order.id,
                title="Order Cancelled — No Rider Found",
                content=f"Order #{str(order.id)[:8]} was cancelled — no rider was available.",
                db=db,
            )
        await db.commit()
