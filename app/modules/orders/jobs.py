from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.orders.services import create_notification
from app.modules.payments.models import PaymentStatus
from app.modules.users.models import NotificationType

ORDER_RESPONSE_TIMEOUT_MINUTES = 5


async def auto_cancel_stale_orders():
    """
    Runs every minute. Finds orders stuck in PLACED status for longer
    than ORDER_RESPONSE_TIMEOUT_MINUTES and auto-cancels them.
    """

    cutoff = datetime.now(UTC) - timedelta(minutes=ORDER_RESPONSE_TIMEOUT_MINUTES)

    async with AsyncSessionLocal as db:

        # fetch all the stale orders
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.payment))
            .where(
                Order.status == OrderStatus.PLACED,
                Order.created_at < cutoff,
            )
        )

        stale_orders = result.scalars().all()

        for order in stale_orders:

            order.status = OrderStatus.CANCELLED
            order.cancellation_resaon = CancellationReason.RESTAURANT_TIMEOUT
            order.canceled_at = datetime.now(UTC)

            if order.payment:
                order.payment.status = PaymentStatus.REFUNDED
                order.payment.refunded_at = datetime.now(UTC)
                # TODO: actually call Razorpay refund API (Phase 6)

            await create_notification(
                user_id=order.user_id,
                type=NotificationType.ORDER_CANCELLED,
                reference_id=order.id,
                title="Order Cancelled",
                content="The restaurant didn't respond in time. Your payment will be refunded.",
                db=db,
            )

        await db.commit()
