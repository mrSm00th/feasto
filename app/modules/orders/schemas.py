import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.orders.models import CancellationReason, OrderStatus
from app.modules.payments.models import PaymentProvider, PaymentStatus

# Order Items


class OrderItemResponseSchema(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    item_name: str
    item_description: str | None
    quantity: int
    item_price: Decimal
    total_price: Decimal

    model_config = ConfigDict(from_attributes=True)


# ── Payment (nested inside order response) ─────────────────────────────────


class PaymentResponseSchema(BaseModel):
    id: uuid.UUID
    provider: PaymentProvider
    amount: Decimal
    status: PaymentStatus
    provider_order_id: str | None
    provider_payment_id: str | None
    failure_reason: str | None
    initiated_at: datetime
    completed_at: datetime | None
    refunded_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


# ── Order ────────────────────────────────────────────────────────────────


class OrderResponseSchema(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    restaurant_id: uuid.UUID
    restaurant_name: str

    address_id: uuid.UUID
    delivery_address: str
    delivery_latitude: Decimal | None
    delivery_longitude: Decimal | None

    customer_name: str
    customer_phone: str | None
    customer_email: str | None

    status: OrderStatus
    cancellation_reason: CancellationReason | None
    cancellation_note: str | None
    special_instructions: str | None

    subtotal: Decimal
    delivery_fee: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal

    payment_method: PaymentProvider

    placed_at: datetime | None
    confirmed_at: datetime | None
    preparing_at: datetime | None
    ready_at: datetime | None
    rider_assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    estimated_ready_at: datetime | None

    created_at: datetime
    updated_at: datetime

    items: list[OrderItemResponseSchema]
    payment: PaymentResponseSchema | None

    model_config = ConfigDict(from_attributes=True)


# ── Restaurant-facing: incoming order list ──────────────────────────────────


class IncomingOrdersResponseSchema(BaseModel):
    total: int
    orders: list[OrderResponseSchema]


# ── Restaurant-facing: accept / reject ──────────────────────────────────────


class AcceptOrderSchema(BaseModel):
    estimated_prep_minutes: int = Field(gt=0, le=120)


class RejectOrderSchema(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
