import asyncio
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.razorpay_client import razorpay_client
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus


async def refund_payment(payment: Payment, reason: str, db: AsyncSession) -> None:
    """
    Initiate a refund for a payment.

    Does not commit the transaction.
    """
    if payment.status != PaymentStatus.PAID:
        # Nothing to refund — either never paid, already refunded
        return

    if payment.provider == PaymentProvider.COD:
        payment.status = PaymentStatus.REFUNDED
        payment.refunded_at = datetime.now(UTC)
        return

    if payment.provider == PaymentProvider.RAZORPAY:
        if not payment.provider_payment_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cannot refund: payment has no provider reference",
            )

        try:
            await asyncio.to_thread(
                razorpay_client.payment.refund,
                payment.provider_payment_id,
                {
                    "amount": int(payment.amount * 100),  # paise, full refund
                    "notes": {"reason": reason},
                },
            )
        except Exception as exc:
            payment.failure_reason = f"Refund initiation failed: {exc}"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to initiate refund. Please try again or contact support.",
            ) from exc

        # Mark refunded immediately. For production, implementing a
        # REFUND_PENDING state until webhook confirmation.
        payment.status = PaymentStatus.REFUNDED
        payment.refunded_at = datetime.now(UTC)
        return

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Refunds not yet implemented for provider {payment.provider.value}",
    )
