import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.rider_applications.models import (
    IdentityProofType,
    RiderApplicationStatus,
    VehicleType,
)

# start a new rider application


class StartApplicationSchema(BaseModel):
    city: Annotated[str, Field(min_lenth=1, max_length=100)]


class RiderApplicationResponseSchema(BaseModel):
    id: uuid.UUID
    applicant_id: uuid.UUID
    status: RiderApplicationStatus

    city_id: uuid.UUID

    identity_proof_type: IdentityProofType | None
    identity_proof_image: str | None
    profile_image: str | None

    vehicle_type: VehicleType | None
    vehicle_number: str | None
    license_expiry_date: date | None
    license_image: str | None

    rejection_reason: str | None
    reviewed_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncomingRiderApplicationsResponseSchema(BaseModel):
    total: int
    applications: list[RiderApplicationResponseSchema]


# admin facing routes schema


class RejectApplicationSchema(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RiderApplicationAdminDetailSchema(RiderApplicationResponseSchema):
    """
    Extends the standard response with decrypted PII — only ever
    returned from the admin-only detail route, never the list route.
    """

    identity_proof_number: str
    license_number: str
