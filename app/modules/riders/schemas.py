import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.orders.schemas import OrderResponseSchema
from app.modules.rider_applications.models import VehicleType
from app.modules.riders.models import RiderProfileStatus


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class AvailableOrderSchema(BaseSchema):
    """
    What the rider sees when browsing available orders —
    showing just the general area (not the exact full address)
    Full address only revealed after the rider accepts and is
    en route to deliver.
    """

    order_id: uuid.UUID
    restaurant_name: str
    restaurant_latitude: Decimal | None
    restaurant_longitude: Decimal | None
    delivery_area: str  # city/area — not the full address
    delivery_fee: Decimal
    estimated_distance_km: float | None
    item_count: int
    placed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
