import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.restaurants.models import CuisineRequestHistory, RestaurantStatus
from app.modules.users.models import UserRole, UserStatus


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseSchema):

    full_name: Annotated[str, Field(min_length=3, max_length=100)]
    email: EmailStr
    phone_number: Annotated[str, Field(min_length=7, max_length=15)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


class UserPublic(BaseSchema):

    full_name: str
    role: UserRole
    user_status: UserStatus
    is_account_verified: bool


class UserPrivate(UserPublic):

    email: EmailStr
    phone_number: str


class RestaurantList(BaseSchema):

    id: uuid.UUID
    name: str
    address_line_1: str
    city: str
    state: str
    status: RestaurantStatus


class PaginatedOwnerRestaurant(BaseSchema):

    restaurants: list[RestaurantList]
    total: int
    skip: int
    limit: int
    has_more: bool


class CuisineRequestHistroryResponse(BaseSchema):

    id: uuid.UUID
    cuisine_name: str
