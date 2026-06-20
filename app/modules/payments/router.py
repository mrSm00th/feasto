import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import require_roles
from app.core.razorpay_client import razorpay_client
from app.db.database import get_db
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.services import (
    add_order_notification,
    push_new_order_to_restaurant,
)
from app.modules.orders.tasks import check_order_timeout
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.payments.schemas import InitiatePaymentResponseSchema
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/orders/{order_id}/initiate",
    response_model=InitiatePaymentResponseSchema,
    status_code=status.HTTP_200_OK,
)
async def initiate_payment(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    # fetch and verify order
    # - order must belong to this user and awaiting payment

    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status != OrderStatus.AWAITING_PAYMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order is not awaiting payment",
        )

    # Fetch the payment row created during checkout
    result = await db.execute(select(Payment).where(Payment.order_id == order.id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")

    #    If order already has a provider_order_id, return it — not creating duplicate
    #    handling the case where user hits "pay" twice
    if payment.provider_order_id:
        return InitiatePaymentResponseSchema(
            razorpay_order_id=payment.provider_order_id,
            razorpay_key_id=settings.razorpay_key_id,
            amount=int(payment.amount * 100),  # razorpay uses paise
            currency="INR",
            order_id=order.id,
        )

    #    Creating Razorpay order
    #    amount is in paise (1 INR = 100 paise)

    try:
        razorpay_order = await asyncio.to_thread(
            razorpay_client.order.create,
            {
                "amount": int(order.total_amount * 100),
                "currency": "INR",
                "receipt": str(order.id),  # the internal order ID
                "notes": {
                    "order_id": str(order.id),
                    "user_id": str(current_user.id),
                },
            },
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create payment order. Please try again.",
        )

    # Store the Razorpay order ID on Payment row
    payment.provider_order_id = razorpay_order["id"]
    await db.commit()

    return InitiatePaymentResponseSchema(
        razorpay_order_id=razorpay_order["id"],
        razorpay_key_id=settings.razorpay_key_id,
        amount=int(order.total_amount * 100),
        currency="INR",
        order_id=order.id,
    )


# webhook route that razorpay call after payment initiation
@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
)
async def razorpay_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Reading raw body - as raw bytes are needed for HMAC calculation
    # parsing JSON first may change the bytes
    raw_body = await request.body()

    # Verify webhook signature -
    #    Razorpay sends X-Razorpay-Signature in the header
    #    so by recomputing the HMAC and comparing them to know whether they match or not

    razorpay_signature = request.headers.get("X-Razorpay-Signature")

    if not razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing signature",
        )

    expected_signature = hmac.new(
        key=settings.razorpay_webhook_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Using hmac.compare_digest as its timing-safe comparison
    # ot using Regular == comparison as its vulnerable to timing attacks
    if not hmac.compare_digest(expected_signature, razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Parsing the event
    payload = json.loads(raw_body)
    event = payload.get("event")

    # then Routing by event type
    if event == "payment.captured":
        await handle_payment_captured(payload, db)

    elif event == "payment.failed":
        await handle_payment_failed(payload, db)

    # always returning 200, for other status code the webhook keeps retrying
    return {"status": "ok"}


# handler function
async def handle_payment_captured(payload: dict, db: AsyncSession):
    payment_entity = payload["payload"]["payment"]["entity"]

    razorpay_order_id = payment_entity["order_id"]
    razorpay_payment_id = payment_entity["id"]
    captured_amount = Decimal(payment_entity["amount"]) / 100  # paise → rupees

    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.order))
        .where(Payment.provider_order_id == razorpay_order_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        return

    if payment.status == PaymentStatus.PAID:
        return

    # confirming if the captured payment amount matches the order amount
    if captured_amount != payment.amount:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = (
            f"Amount mismatch: expected {payment.amount}, captured {captured_amount}"
        )
        await db.commit()
        # TODO: generate an alert as this scenario is suspecious
        return

    now = datetime.now(UTC)
    payment.status = PaymentStatus.PAID
    payment.provider_payment_id = razorpay_payment_id
    payment.completed_at = now

    payment.order.status = OrderStatus.PLACED
    payment.order.placed_at = now

    # fetch order by the razor
    order_id = payload["payload"]["payment"]["entity"]["notes"]["order_id"]
    user_id = payload["payload"]["payment"]["entity"]["notes"]["user_id"]

    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == user_id,
        )
    )

    order = result.scalar_one_or_none()

    if not order:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="order not found"
        )
    notification = await add_order_notification(order, db)
    db.add(notification)

    # NOTE: importing cart here to prevent any circular import issues
    from app.modules.carts.models import Cart

    result = await db.execute(select(Cart).where(Cart.user_id == payment.order.user_id))
    cart = result.scalar_one_or_none()
    if cart:
        await db.delete(cart)

    await db.commit()

    await push_new_order_to_restaurant(order, db)

    # Schedule the timeout check — countdown is in seconds
    check_order_timeout.apply_async(
        args=[str(payment.order.id)],
        countdown=settings.order_response_timeout_minutes * 60,
    )


async def handle_payment_failed(payload: dict, db: AsyncSession):
    payment_entity = payload["payload"]["payment"]["entity"]
    razorpay_order_id = payment_entity["order_id"]
    failure_reason = payment_entity.get("error_description", "Payment failed")

    result = await db.execute(
        select(Payment)
        .options(selectinload(Payment.order))
        .where(Payment.provider_order_id == razorpay_order_id)
    )
    payment = result.scalar_one_or_none()

    if not payment or payment.status != PaymentStatus.PENDING:
        return

    payment.status = PaymentStatus.FAILED
    payment.failure_reason = failure_reason

    # Order stays AWAITING_PAYMENT — user can retry
    # not canceling  the order on first failure

    await db.commit()
