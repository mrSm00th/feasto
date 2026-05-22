import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.restaurants.models import RestaurantStatus


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class RestaurantCreate(BaseSchema):

    name: Annotated[str, Field(min_length=1, max_length=120)]
    phone_number: Annotated[str, Field(min_length=7, max_length=20)]
    address_line_1: Annotated[str, Field(min_length=1, max_length=255)]
    address_line_2: Annotated[str | None, Field(max_length=255)] = None
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    country: Annotated[str, Field(min_length=1, max_length=100)]


class RestaurantCreateResponse(RestaurantCreate):
    id: uuid.UUID
    status: RestaurantStatus


class RestaurantDocumentsUpload(BaseSchema):

    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]


class RestaurantDocumentsUploadResponse(RestaurantDocumentsUpload):

    id: uuid.UUID
    status: RestaurantStatus


class ImageResponse(BaseSchema):

    id: uuid.UUID
    image_path: str


class RestaurantImageUploadResponse(BaseSchema):

    uploaded: Annotated[int, Field(max_length=5)]
    images: list[ImageResponse]


class PrimaryImageUpdate(BaseSchema):

    id: uuid.UUID
    image_path: str
    is_primary: bool
