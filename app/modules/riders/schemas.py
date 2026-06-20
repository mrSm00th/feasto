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


class OnlineStatusSchema(BaseModel):
    go_online: bool


class RiderProfileResponseSchema(BaseSchema):

    id: uuid.UUID
    user_id: uuid.UUID
    profile_image: str | None
    status: RiderProfileStatus
    is_online: bool
    is_available: bool
    vehicle_type: VehicleType | None
    vehicle_number: str | None
    avg_rating: Decimal
    total_reviews: int
    total_deliveries: int
    current_latitude: Decimal | None
    current_longitude: Decimal | None
    last_location_update: datetime | None
    created_at: datetime


class LocationUpdateSchema(BaseSchema):
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
