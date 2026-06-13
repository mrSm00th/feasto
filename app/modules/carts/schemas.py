import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.modules.payments.models import PaymentProvider, PaymentStatus
from app.modules.orders.models import OrderStatus
from datetime import datetime


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Request schemas ---


class CartItemEntry(BaseSchema):
    menu_item_id: uuid.UUID
    quantity: Annotated[
        int,
        Field(gt=0, description="Desired final quantity — set semantics, not a delta"),
    ]


class CartAddItemSchema(BaseSchema):
    restaurant_id: uuid.UUID
    items: list[CartItemEntry]


class CartItemRemoveSchema(BaseSchema):
    quantity: int = Field(..., gt=0, description="How many units to remove")


# --- Response schemas ---


class CartItemResponseSchema(BaseSchema):
    id: uuid.UUID  # cart_item_id — use this for PATCH/DELETE calls
    menu_item_id: uuid.UUID  # use this to correlate with the menu catalog
    name: str
    quantity: int
    price: Decimal


class CartResponseSchema(BaseSchema):
    cart_id: uuid.UUID | None = None
    restaurant_id: uuid.UUID | None = None
    items: list[CartItemResponseSchema]
    total_price: Decimal




class CartCheckoutSchema(BaseSchema):
    address_id: uuid.UUID
    payment_method: PaymentProvider
    special_instructions: str | None = Field(
        default=None,
        max_length=250,
    )

    @field_validator("special_instructions", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

class CartCheckoutSchema(BaseModel):
    address_id: uuid.UUID
    payment_method: PaymentProvider
    special_instructions: str | None = Field(None, max_length=500)


# schemas.py in orders module (response)

class OrderItemResponseSchema(BaseModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID
    item_name: str
    item_description: str | None
    quantity: int
    item_price: Decimal
    total_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class PaymentResponseSchema(BaseModel):
    id: uuid.UUID
    provider: PaymentProvider
    amount: Decimal
    status: PaymentStatus
    provider_order_id: str | None   # frontend needs this to open Razorpay sheet

    model_config = ConfigDict(from_attributes=True)


class OrderResponseSchema(BaseModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    restaurant_name: str

    delivery_address: str
    delivery_latitude: Decimal | None
    delivery_longitude: Decimal | None

    customer_name: str
    customer_phone: str | None
    customer_email: str | None

    status: OrderStatus
    special_instructions: str | None

    subtotal: Decimal
    delivery_fee: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal

    payment_method: PaymentProvider

    placed_at: datetime | None
    estimated_ready_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime

    items: list[OrderItemResponseSchema]
    payment: PaymentResponseSchema | None

    model_config = ConfigDict(from_attributes=True)