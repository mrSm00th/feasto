import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.notifications.models import NotificationType
from app.modules.restaurants.models import CuisineRequestHistory, RestaurantStatus
from app.modules.users.models import UserStatus


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseSchema):

    id: uuid.UUID
    type: NotificationType
    title: str
    # content: str sendng in detailed response
    is_read: bool
    created_at: datetime


class NotificationDetailResponse(NotificationResponse):

    content: str


class PaginatedNotifications(BaseSchema):
    notifications: list[NotificationResponse]
    total: int
    skip: int
    limit: int
    has_more: bool
