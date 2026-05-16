import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: set
    token_type: str


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    RESTURANT_OWNER = "RESTAURANT_OWNER"
    ADMIN = "ADMIN"


class UserCreate(BaseSchema):

    full_name: Annotated[str, Field(min_length=3, max_length=100)]
    email: EmailStr
    phone_number: Annotated[str, Field(min_length=7, max_length=15)]
    password: Annotated[str, Field(min_length=8, max_length=128)]
    role: UserRole
    is_active: Annotated[bool, Field(default=True)]
    is_verified: Annotated[bool, Field(default=True)]


class UserPublic(BaseSchema):

    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool


class userPrivate(UserPublic):

    email: EmailStr
    phone_number: str
