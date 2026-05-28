import uuid
from datetime import UTC, datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.restaurants.models import AvailabilityStatus, RestaurantStatus


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


class RestaurantCreateResponse(RestaurantCreate):
    id: uuid.UUID
    status: RestaurantStatus


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


# Restro Availability Schemas


class ShiftEntry(BaseSchema):
    """
    status=OPEN         → opening_time and closing_time required
    status=CLOSED       → times must be absent
    status=OPEN_24_HOURS → times must be absent, shift_index must be 0
    """

    # 0=Monday … 6=Sunday  (Python datetime.weekday() convention)
    day_of_week: int = Field(..., ge=0, le=6)

    status: AvailabilityStatus

    opening_time: time | None = None
    closing_time: time | None = None

    # 0 = first shift (e.g. lunch), 1 = second shift (e.g. dinner)
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
                if self.closing_time == self.opening_time:
                    raise ValueError("closing_time cannot equal opening_time.")

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

    hours: list[ShiftEntry] = Field(
        ..., min_length=1, max_length=21
    )  # max 7 days × 3 shifts

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
    """
    Replacement schedule for one specific day.
    All existing shifts for that day are replaced by these.

    Send a single entry with status=CLOSED to mark the day as closed.
    """

    shifts: list[ShiftEntry] = Field(..., min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_shifts(self) -> "DayHoursUpdate":
        # All shifts must be for the same day — validated in the route
        # but also guarded here so schema is self-contained
        seen_indices: set[int] = set()
        for shift in self.shifts:
            if shift.shift_index in seen_indices:
                raise ValueError(
                    f"Duplicate shift_index {shift.shift_index} in update payload."
                )
            seen_indices.add(shift.shift_index)

        # If any shift is CLOSED or OPEN_24_HOURS, it must be the only shift
        non_open = [s for s in self.shifts if s.status != AvailabilityStatus.OPEN]
        if non_open and len(self.shifts) > 1:
            raise ValueError(
                f"When status is {non_open[0].status}, only one shift entry is allowed."
            )

        return self


# Availability responses Schemas


class AvailabilityEntryResponse(BaseSchema):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    day_of_week: int
    status: AvailabilityStatus
    opening_time: time | None
    closing_time: time | None
    shift_index: int

    model_config = {"from_attributes": True}


class RestaurantHoursResponse(BaseSchema):
    """Full schedule — ordered by day then shift."""

    hours: list[AvailabilityEntryResponse]


class DayHoursResponse(BaseSchema):
    """Single day's shifts after an update."""

    day_of_week: int
    shifts: list[AvailabilityEntryResponse]


# Closure Schemas


class ClosureCreate(BaseSchema):
    """
    Payload to temporarily close a restaurant.

    starts_at defaults to now if not provided.
    ends_at=None means indefinite — owner must explicitly call DELETE /closure.
    ends_at set to a future datetime = scheduled closure with auto-reopen.
    """

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

    model_config = {"from_attributes": True}


class CuisineResponse(BaseSchema):

    id: uuid.UUID
    cuisine_name: str
    cuisine_slug: str


class CreateCuisine(BaseSchema):

    cuisine_name: str
