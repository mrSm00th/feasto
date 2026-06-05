import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.partner_applications.models import ApplicationStatus


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PartnerApplicationCreate(BaseSchema):

    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]


class PartnerApplicationCreateResponse(
    BaseSchema
):  # only sending the response to the owner

    id: uuid.UUID
    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]

    status: ApplicationStatus
    created_at: datetime
    # rejection_reason: Annotated[str | None, Field(max_length=500)]


class PartnerApplicationMini(BaseSchema):

    id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime


class PaginatedPartnerAppResponse(BaseSchema):
    applications: list[PartnerApplicationMini]
    total: int
    skip: int
    limit: int
    has_more: bool
