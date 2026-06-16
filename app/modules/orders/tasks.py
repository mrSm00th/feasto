import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.orders.service import create_notification

# from app.modules.payments.service import refund_payment
from app.modules.payments.models import PaymentStatus
from app.modules.users.models import NotificationType


@celery_app.task(name="orders.check_order_timeout")
def check_order_timeout(order_id_str: str) -> None:
    """
    Celery entrypoint — must be sync.
    Bridges into the async DB layer via asyncio.run().
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
        # restaurant already responded, or payment already confirmed
        if order.status not in (OrderStatus.PLACED, OrderStatus.AWAITING_PAYMENT):
            return

        # Capture this BEFORE mutating status
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

            if order.payment and order.payment.status == PaymentStatus.PAID:
                order.payment.status = PaymentStatus.REFUNDED
                order.payment.refunded_at = datetime.now(UTC)
                # TODO: actually call Razorpay refund API (Phase 6)

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
