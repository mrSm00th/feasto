import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.locations.models import CityStatus


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class LocationActivateRequest(BaseSchema):

    city_name: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]


class LocationActivateResponse(BaseSchema):

    id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    status: CityStatus
    created_by: uuid.UUID
    created_at: datetime


class LocationInactivationRequest(BaseSchema):

    city_name: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    inactivation_reason: Annotated[str, Field(min_length=1, max_length=250)]


class LocationInactivationResponse(BaseSchema):

    id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    status: CityStatus
    created_at: datetime
    inactivated_at: datetime
    inactivation_reason: Annotated[str, Field(min_length=1, max_length=250)]
