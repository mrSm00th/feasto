# payments/schemas.py
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.modules.payments.models import PaymentProvider, PaymentStatus


class InitiatePaymentResponseSchema(BaseModel):
    razorpay_order_id: str  # frontend passes this to Razorpay SDK
    razorpay_key_id: str  # frontend uses this to initialize Razorpay
    amount: int  # in paise — Razorpay requires this
    currency: str
    order_id: uuid.UUID  # your internal order ID

    model_config = ConfigDict(from_attributes=True)


class PaymentStatusResponseSchema(BaseModel):
    order_id: uuid.UUID
    payment_status: PaymentStatus
    provider: PaymentProvider
    amount: Decimal
    completed_at: str | None

    model_config = ConfigDict(from_attributes=True)
