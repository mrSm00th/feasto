import uuid
from datetime import UTC, datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.restaurants.models import (
    AvailabilityStatus,
    MappedCuisineStatus,
    RestaurantStatus,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RestaurantCreate(BaseSchema):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    phone_number: Annotated[str, Field(min_length=7, max_length=20)]
    address_line_1: Annotated[str, Field(min_length=1, max_length=255)]
    address_line_2: Annotated[str | None, Field(max_length=255)] = None
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    country: Annotated[str, Field(min_length=1, max_length=100)]


class RestaurantCreateResponse(BaseSchema):
    id: uuid.UUID
    status: RestaurantStatus
    name: Annotated[str, Field(min_length=1, max_length=120)]
    phone_number: Annotated[str, Field(min_length=7, max_length=20)]
    address_line_1: Annotated[str, Field(min_length=1, max_length=255)]
    address_line_2: Annotated[str | None, Field(max_length=255)] = None
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    country: Annotated[str, Field(min_length=1, max_length=100)]


class RestaurantDocumentsUpload(BaseSchema):
    fssai_license_number: Annotated[str, Field(min_length=14, max_length=14)]
    gst_number: Annotated[str, Field(min_length=15, max_length=15)]


class RestaurantDocumentsUploadResponse(RestaurantDocumentsUpload):
    id: uuid.UUID
    status: RestaurantStatus


class ImageResponse(BaseSchema):
    id: uuid.UUID
    image_path: str


class RestaurantImageUploadResponse(BaseSchema):
    uploaded: int
    images: list[ImageResponse]


class PrimaryImageUpdate(BaseSchema):
    id: uuid.UUID
    image_path: str
    is_primary: bool


# =========================
# AVAILABILITY SCHEMAS
# =========================


class ShiftEntry(BaseSchema):
    """
    status=OPEN          → opening_time and closing_time required
    status=CLOSED        → times must be absent
    status=OPEN_24_HOURS → times must be absent, shift_index must be 0
    """

    day_of_week: int = Field(..., ge=0, le=6)
    status: AvailabilityStatus
    opening_time: time | None = None
    closing_time: time | None = None
    shift_index: int = Field(default=0, ge=0, le=9)

    @model_validator(mode="after")
    def validate_shift(self) -> "ShiftEntry":
        match self.status:
            case AvailabilityStatus.OPEN:
                if self.opening_time is None or self.closing_time is None:
                    raise ValueError(
                        "opening_time and closing_time are required when status is OPEN."
                    )
                if self.closing_time <= self.opening_time:
                    raise ValueError("closing_time must be after opening_time.")
            case AvailabilityStatus.CLOSED | AvailabilityStatus.OPEN_24_HOURS:
                if self.opening_time is not None or self.closing_time is not None:
                    raise ValueError(
                        f"opening_time and closing_time must be absent when status is {self.status}."
                    )
                if (
                    self.status == AvailabilityStatus.OPEN_24_HOURS
                    and self.shift_index != 0
                ):
                    raise ValueError("shift_index must be 0 for OPEN_24_HOURS days.")
        return self


class RestaurantHoursUpload(BaseSchema):
    hours: list[ShiftEntry] = Field(..., min_length=1, max_length=21)

    @model_validator(mode="after")
    def validate_no_duplicate_shifts(self) -> "RestaurantHoursUpload":
        seen: set[tuple[int, int]] = set()
        for entry in self.hours:
            key = (entry.day_of_week, entry.shift_index)
            if key in seen:
                day_name = [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ][entry.day_of_week]
                raise ValueError(
                    f"Duplicate shift_index {entry.shift_index} for {day_name}. "
                    "Each shift on a day must have a unique shift_index."
                )
            seen.add(key)
        return self


class DayHoursUpdate(BaseSchema):
    """Replacement schedule for one specific day. All existing shifts are replaced."""

    shifts: list[ShiftEntry] = Field(..., min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_shifts(self) -> "DayHoursUpdate":
        seen_indices: set[int] = set()
        for shift in self.shifts:
            if shift.shift_index in seen_indices:
                raise ValueError(
                    f"Duplicate shift_index {shift.shift_index} in update payload."
                )
            seen_indices.add(shift.shift_index)
        non_open = [s for s in self.shifts if s.status != AvailabilityStatus.OPEN]
        if non_open and len(self.shifts) > 1:
            raise ValueError(
                f"When status is {non_open[0].status}, only one shift entry is allowed."
            )
        return self


class AvailabilityEntryResponse(BaseSchema):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    day_of_week: int
    status: AvailabilityStatus
    opening_time: time | None
    closing_time: time | None
    shift_index: int


class RestaurantHoursResponse(BaseSchema):
    hours: list[AvailabilityEntryResponse]


class DayHoursResponse(BaseSchema):
    day_of_week: int
    shifts: list[AvailabilityEntryResponse]


# =========================
# CLOSURE SCHEMAS
# =========================


class ClosureCreate(BaseSchema):
    reason: str | None = Field(default=None, max_length=500)
    starts_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "ClosureCreate":
        if self.ends_at is not None:
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at.")
            if self.ends_at <= datetime.now(UTC):
                raise ValueError("ends_at must be in the future.")
        return self


class ClosureResponse(BaseSchema):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    reason: str | None
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime


# =========================
# CUISINE SCHEMAS
# =========================


class CuisineResponse(BaseSchema):
    """Single approved CuisineType — used in catalog listing."""

    id: uuid.UUID
    cuisine_name: str
    cuisine_slug: str


class CuisineListResponse(BaseSchema):
    """Paginated catalog of all approved cuisines."""

    cuisines: list[CuisineResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class CreateCuisine(BaseSchema):
    cuisine_name: str


class CuisineAdd(BaseSchema):
    cuisine_id: uuid.UUID


class CuisineMappingResponse(BaseSchema):
    """
    A restaurant's cuisine mapping row.
    cuisine is None when status=PENDING_REVIEW (no CuisineType yet).
    """

    id: uuid.UUID
    cuisine_id: uuid.UUID | None
    request_id: uuid.UUID | None
    status: MappedCuisineStatus
    is_primary: bool
    created_at: datetime
    cuisine: CuisineResponse | None = None


class CuisineAddResponse(BaseSchema):
    """Returned after successfully adding an approved cuisine to a restaurant."""

    id: uuid.UUID
    cuisine_id: uuid.UUID
    cuisine_name: str
    cuisine_slug: str
    status: MappedCuisineStatus
    created_at: datetime


class RestaurantCuisineListResponse(BaseSchema):
    """All cuisine mappings for a restaurant (active + pending)."""

    cuisines: list[CuisineMappingResponse]
    total: int
    restaurant_id: uuid.UUID


class RestaurantPendingCuisineItem(BaseSchema):
    """A single pending cuisine request row joined with CuisineRequest details."""

    mapping_id: uuid.UUID
    request_id: uuid.UUID
    cuisine_name: str
    cuisine_slug: str
    status: MappedCuisineStatus
    is_primary: bool
    created_at: datetime


class RestaurantCuisineRequestListResponse(BaseSchema):
    """All pending cuisine requests for a restaurant."""

    requests: list[RestaurantPendingCuisineItem]
    total: int
    restaurant_id: uuid.UUID


class RestaurantPrimaryCuisneRequest(BaseSchema):
    cuisine_id: uuid.UUID


class RestaurantPrimaryCuisineResponse(BaseSchema):
    """Returned after setting or changing the primary cuisine."""

    id: uuid.UUID
    cuisine_id: uuid.UUID
    status: MappedCuisineStatus
    is_primary: bool
    created_at: datetime
    cuisine: CuisineResponse | None = None


# =========================
# IMAGE SCHEMAS
# =========================


class RestaurantPrimaryImageResponse(BaseSchema):
    id: uuid.UUID
    image_path: str
