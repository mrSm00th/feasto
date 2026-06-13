import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddressCreateSchema(BaseModel):
    label: str | None = Field(default=None, max_length=50)
    address_line_1: str = Field(min_length=3, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(min_length=2, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_default: bool = False

    @field_validator("label", "address_line_2", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator(
        "address_line_1", "city", "state", "postal_code", "country", mode="before"
    )
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class AddressPatchSchema(BaseModel):

    label: str | None = Field(default=None, max_length=50)
    address_line_1: str | None = Field(default=None, min_length=3, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_default: bool | None = None

    @field_validator("label", "address_line_2", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class AddressResponseSchema(BaseModel):
    id: uuid.UUID
    label: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    latitude: Decimal | None
    longitude: Decimal | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddressListResponseSchema(BaseModel):
    total: int
    addresses: list[AddressResponseSchema]
