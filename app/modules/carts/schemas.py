import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


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
