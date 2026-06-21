import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.razorpay_client import razorpay_client
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus

logger = logging.getLogger(__name__)


async def initiate_refund(
    order_id: str | uuid.UUID,
    reason: str,
    db: AsyncSession,
) -> Payment | None:

    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.order))
        .where(Payment.order_id == order_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        logger.warning("initiate_refund: no payment found for order %s", order_id)
        return None

    if payment.status in (PaymentStatus.REFUNDED, PaymentStatus.REFUND_PENDING):
        return payment

    if payment.status != PaymentStatus.PAID:

        logger.info(
            "initiate_refund: payment %s for order %s is %s, not PAID — skipping",
            payment.id,
            order_id,
            payment.status,
        )
        return None

    if payment.provider == PaymentProvider.COD:

        payment.status = PaymentStatus.REFUNDED
        payment.refunded_at = datetime.now(UTC)
        return payment

    if payment.provider == PaymentProvider.RAZORPAY:
        if not payment.provider_payment_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cannot refund: payment has no provider reference",
            )

        try:
            refund = await asyncio.to_thread(
                razorpay_client.payment.refund,
                payment.provider_payment_id,
                {
                    "amount": int(payment.amount * 100),  # paise, full refund
                    "notes": {"reason": reason, "order_id": str(order_id)},
                },
            )
        except Exception as exc:
            payment.refund_failure_reason = f"Refund initiation failed: {exc}"
            logger.exception(
                "Refund initiation failed for payment %s (order %s)",
                payment.id,
                order_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to initiate refund. Please try again or contact support.",
            ) from exc

        payment.status = PaymentStatus.REFUND_PENDING
        payment.provider_refund_id = refund["id"]
        payment.refund_initiated_at = datetime.now(UTC)
        return payment

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Refunds not yet implemented for provider {payment.provider.value}",
    )
