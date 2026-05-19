import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.owner_applications.models import ApplicationStatus


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnerApplicationCreate(BaseSchema):

    restaurant_name: Annotated[str, Field(min_length=3, max_length=100)]
    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]
    # pan_number: Annotated[str, Field(min_length=10, max_length=10)]
    # bank_account_number: Annotated[str, Field(min_length=15, max_length=20)]


class OwnerApplicationResponse(
    OwnerApplicationCreate
):  # only sending the response to the owner

    # restaurant_name: Annotated[str, Field(min_length=3, max_length=100)]
    # fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    # gst_number: Annotated[str, Field(min_length=15, max_length= 15)]

    # pan_number: Annotated[str, Field(min_length=10, max_length=10)]
    # bank_account_number: Annotated[str, Field(min_length=15, max_length=20)]
    id: uuid.UUID
    status: ApplicationStatus
    rejection_reason: Annotated[str | None, Field(max_length=500)]
