import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.menus.models import MenuCategoryStatus, MenuItemStatus
from app.modules.restaurants.models import VegType


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class MenuCategoryCreateRequest(BaseSchema):

    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    # Auto filling fro this field
    # sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuCategoryCreateResponse(BaseSchema):

    id: uuid.UUID
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str | None, Field(min_length=1, max_length=500)] = None
    sort_order: Annotated[int, Field(ge=0, le=100)]
    created_at: datetime


class MenuItemCreate(BaseSchema):

    name: Annotated[str, Field(min_length=1, max_length=255)]
    description: Annotated[str | None, Field(min_length=10, max_length=500)] = None
    price: Annotated[float, Field(gt=0.0, le=100000.0)]
    discounted_price: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    veg_type: VegType
    is_available: bool = True
    preparation_time_minutes: Annotated[int, Field(gt=0, le=1440)]
    calories: Annotated[int | None, Field(gt=0, le=100000)] = None

    # Field now auto filled by server
    # sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuItemCreateResponse(BaseSchema):

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    price: float
    discounted_price: float | None
    veg_type: VegType
    is_available: bool
    preparation_time_minutes: int
    calories: int | None
    created_at: datetime
    sort_order: int


class ItemImageResponse(BaseSchema):

    id: uuid.UUID
    image_path: str


class ImageResponse(BaseSchema):

    id: uuid.UUID
    image_path: str


class RestaurantDiningMenuUploadResponse(BaseSchema):

    uploaded: int
    images: list[ImageResponse]


# Schema for menu category reorder request
class MenuCategoryReorderRequest(BaseSchema):

    category_ids: list[uuid.UUID]


# Schema for Menu Categor object - used for list of categories
class MenuCategoryOrder(BaseSchema):

    id: uuid.UUID  # menu category id
    sort_order: Annotated[int, Field(ge=1, le=100)]


# schema for menu category request response
class MenuCategoryReorderResponse(BaseSchema):

    categories: list[MenuCategoryOrder]
    total_categories: int
    restaurant_id: uuid.UUID


# schema for  request to sort menu items under a category
class MenuCategoryItemReorderRequest(BaseSchema):

    menu_item_ids: list[uuid.UUID]


# schema for the MenuItem object send as list of response
class MenuCategoryItemOrder(BaseSchema):

    id: uuid.UUID  # menu_item.id
    sort_order: Annotated[int, Field(ge=1, le=100)]


# schema for reordering menu item response
class MenuCategoryItemReorderResponse(BaseSchema):

    menu_items: list[MenuCategoryItemOrder]
    total_items: int
    category_id: uuid.UUID
    restaurant_id: uuid.UUID


# schema for - get_all_menu_categories_for_restaurant


class MenuCategorySchema(BaseSchema):

    id: uuid.UUID  # menu_item.id
    status: MenuCategoryStatus
    name: str
    normalized_name: str
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Annotated[datetime | None, Field(default=None)] = None
    sort_order: Annotated[int, Field(ge=1, le=100)]


# list response to show all menu categories
class MenuCategoryListResponse(BaseSchema):
    menu_categories: list[MenuCategorySchema]
    total_categories: int
    restaurant_id: uuid.UUID
    skip: int
    limit: int
    has_more: bool


# schema to get all the menu items under a category
class MenuItemSchema(BaseSchema):

    id: uuid.UUID  # menu_item.id
    category_id: uuid.UUID
    status: MenuItemStatus
    name: str
    normalized_name: str
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None
    price: Decimal
    discounted_price: Decimal | None = None
    image_url: str | None = None
    veg_type: VegType
    is_available: bool
    preparation_time_minutes: int | None = None
    calories: int | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: Annotated[datetime | None, Field(default=None)] = None
    sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuItemPaginatedResponse(BaseSchema):

    menu_items: list[MenuItemSchema]
    category_id: uuid.UUID
    restaurant_id: uuid.UUID
    total: int
    skip: int
    limit: int
    has_more: bool


class MenuCategoryUpdateRequest(BaseSchema):

    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None


class MenuCategoryUpdateResponse(BaseSchema):

    id: uuid.UUID  # menu_item.id
    status: MenuCategoryStatus
    name: str
    normalized_name: str
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None
    created_at: datetime
    updated_at: datetime
    sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuCategoryArchiveResponse(BaseSchema):

    id: uuid.UUID  # menu_item.id
    status: MenuCategoryStatus
    name: str
    normalized_name: str
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime
    sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuCategoryUnarchiveResponse(BaseSchema):

    id: uuid.UUID  # menu_item.id
    status: MenuCategoryStatus
    name: str
    normalized_name: str
    description: Annotated[str | None, Field(min_length=1, max_length=350)] = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    sort_order: Annotated[int, Field(ge=1, le=100)]


class MenuItemUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = None
    discounted_price: Decimal | None = None
    clear_discounted_price: bool = False
    veg_type: VegType | None = None
    preparation_time_minutes: int | None = None
    calories: int | None = None


class MenuItemAvailabilityRequest(BaseModel):
    is_available: bool


class MenuItemUpdateResponse(BaseModel):
    # full item fields
    model_config = ConfigDict(from_attributes=True)


class MenuCategorySchema(BaseSchema):
    id: uuid.UUID
    name: str
    description: str | None
    sort_order: int
    # status intentionally excluded — customer only sees ACTIVE,
    # no need to expose it in the response


class MenuCategoryPaginatedResponse(BaseSchema):
    categories: list[MenuCategorySchema]
    restaurant_id: uuid.UUID
    total: int
    skip: int
    limit: int
    has_more: bool


class MenuItemImageSchema(BaseSchema):
    id: uuid.UUID
    image_url: str  # resolve to public URL at route level if needed


class MenuItemSchema(BaseSchema):
    id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    veg_type: VegType
    is_available: bool
    sort_order: int
    image: MenuItemImageSchema | None
    # status excluded — customer only ever sees ACTIVE items


class MenuItemPaginatedResponse(BaseSchema):
    items: list[MenuItemSchema]
    category_id: uuid.UUID
    restaurant_id: uuid.UUID
    total: int
    skip: int
    limit: int
    has_more: bool
