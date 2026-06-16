from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.orders.service import create_notification
from app.modules.payments.models import PaymentStatus
from app.modules.users.models import NotificationType

ORDER_RESPONSE_TIMEOUT_MINUTES = 5


async def auto_cancel_stale_orders():
    """
    Runs every minute. Cancels two distinct categories of stuck orders:
      - AWAITING_PAYMENT past timeout → customer abandoned checkout,
        nothing was charged, no refund needed
      - PLACED past timeout → restaurant never responded, payment WAS
        captured, refund required
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=ORDER_RESPONSE_TIMEOUT_MINUTES)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.payment))
            .where(
                Order.status.in_([OrderStatus.PLACED, OrderStatus.AWAITING_PAYMENT]),
                Order.created_at < cutoff,
            )
        )
        stale_orders = result.scalars().all()

        for order in stale_orders:
            was_awaiting_payment = order.status == OrderStatus.AWAITING_PAYMENT

            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now(UTC)

            if was_awaiting_payment:
                order.cancellation_reason = CancellationReason.PAYMENT_FAILED
                order.cancellation_note = "Payment was not completed in time"
                # No refund — nothing was ever captured
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
