import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.partner_applications.models import ApplicationStatus
from app.modules.users.schemas import UserPublic


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PendingApplicationsList(BaseSchema):

    id: uuid.UUID
    applicant: UserPublic
    status: ApplicationStatus
    created_at: datetime


class PaginatedApplicationResponse(BaseSchema):
    applications: list[PendingApplicationsList]
    total: int
    skip: int
    limit: int
    has_more: bool


class PartnerApplicationDetailed(BaseSchema):

    id: uuid.UUID
    applicant: UserPublic
    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]
    status: ApplicationStatus
    rejection_reason: Annotated[str | None, Field(max_length=500)]
    created_at: datetime


class PartnerApplicationAdminReview(
    BaseSchema
):  # only sending the response to the admin so full info

    id: uuid.UUID
    applicant: UserPublic
    status: ApplicationStatus
    rejection_reason: Annotated[str | None, Field(max_length=500)] = None
    reviewed_by: uuid.UUID
    reviewed_at: datetime
