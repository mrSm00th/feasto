import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.owner_applications.models import ApplicationStatus
from datetime import datetime


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnerApplicationCreate(BaseSchema):

    restaurant_name: Annotated[str, Field(min_length=3, max_length=100)]
    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]

class OwnerApplicationResponse(
    OwnerApplicationCreate
):  # only sending the response to the owner

    id: uuid.UUID
    status: ApplicationStatus
    rejection_reason: Annotated[str | None, Field(max_length=500)]

class OwnerApplicationMini(BaseSchema):

    id: uuid.UUID
    restaurant_name: str
    status: ApplicationStatus
    created_at: datetime


class PaginatedOwnerAppResponse(BaseSchema):
    applications: list[OwnerApplicationMini]
    total: int
    skip: int
    limit: int
    has_more: bool