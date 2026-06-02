import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.restaurants.models import VegType


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class CreateMenuCategory(BaseSchema):

    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    display_order: Annotated[int, Field(ge=0, le=100)]


class MenuCategoryCreateResponse(CreateMenuCategory):

    id: uuid.UUID
    created_at: datetime


class MenuItemCreate(BaseSchema):

    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: Annotated[str | None, Field(min_length=10, max_length=500)] = None
    price: Annotated[float, Field(gt=0.0, le=100000.0)]
    discounted_price: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    veg_type: VegType
    is_available: bool = True
    preparation_time_minutes: Annotated[int, Field(gt=0, le=1440)]
    calories: Annotated[int | None, Field(gt=0, le=100000)] = None


class MenuItemResponse(BaseSchema):

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    price: float
    discounted_price: float | None
    veg_type: VegType
    is_available: bool
    preparation_time_minutes: int
    calories: int | None
    created_at: datetime


class ItemImageResponse(BaseSchema):

    id: uuid.UUID
    image_path: str
