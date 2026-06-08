from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class AvailabilityStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    OPEN_24_HOURS = "OPEN_24_HOURS"


class VegType(str, enum.Enum):
    VEG = "VEG"
    NON_VEG = "NON_VEG"


class DayOfWeek(str, enum.Enum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class RestaurantStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    BASIC_INFO_ADDED = "BASIC_INFO_ADDED"
    DOCUMENTS_ADDED = "DOCUMENTS_ADDED"
    MENU_ADDED = "MENU_ADDED"
    SUBMITTED = "SUBMITTED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    fssai_license_number: Mapped[str] = mapped_column(
        String(14),
        unique=False,
        nullable=True,
        index=True,
    )

    gst_number: Mapped[str] = mapped_column(
        String(15),
        unique=False,
        nullable=True,
        index=True,
    )

    cuisine_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    veg_type: Mapped[VegType] = mapped_column(
        Enum(VegType),
        default=VegType.VEG,
    )

    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    address_line_1: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    normalized_address_line_1: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    address_line_2: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    normalized_city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    postal_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        index=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
        index=True,
    )

    # when the owner temporarily closes the restaurant for the day or for a specific period
    # they can set this flag to true. This will help in hiding the restaurant from the customers during that period.
    is_manually_closed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # admin level control
    status: Mapped[RestaurantStatus] = mapped_column(
        Enum(RestaurantStatus),
        default=RestaurantStatus.DRAFT,
    )

    is_submitted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    avg_rating: Mapped[Decimal] = mapped_column(
        Numeric(2, 1),
        default=0,
    )

    total_reviews: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # relationships
    owner: Mapped["User"] = relationship(
        back_populates="restaurants",
    )

    categories: Mapped[list["MenuCategory"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    menu_item_images: Mapped[list["MenuItemImage"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    restaurant_images: Mapped[list["RestaurantImage"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    primary_image: Mapped["RestaurantImage | None"] = relationship(
        primaryjoin=(
            "and_(Restaurant.id == RestaurantImage.restaurant_id, "
            "RestaurantImage.is_primary == True)"
        ),
        uselist=False,
        viewonly=True,
        lazy="raise",
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="restaurant",
    )

    availability: Mapped[list["RestaurantAvailability"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    # Temporary closure events (maintenance, holidays, emergencies)
    closures: Mapped[list["RestaurantClosure"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    restaurant_cuisines: Mapped[list["RestaurantCuisineMapping"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            owner_id, normalized_name, normalized_address_line_1, normalized_city
        ),
    )


class RestaurantAvailability(Base):
    __tablename__ = "restaurant_availability"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 0 = Monday, 6 = Sunday
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus),
        nullable=False,
    )

    # Only used when status == OPEN
    opening_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    closing_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    # Supports multiple shifts (0,1,2...)
    shift_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    restaurant: Mapped["Restaurant"] = relationship(back_populates="availability")

    __table_args__ = (
        # Fast lookup for availability queries
        Index(
            "ix_availability_restaurant_day",
            "restaurant_id",
            "day_of_week",
        ),
        # Prevent duplicate shifts per day
        UniqueConstraint(
            "restaurant_id",
            "day_of_week",
            "shift_index",
            name="uq_restaurant_day_shift",
        ),
        # OPEN must have both times
        CheckConstraint(
            """
            NOT (
                status = 'OPEN'
                AND (opening_time IS NULL OR closing_time IS NULL)
            )
            """,
            name="ck_open_requires_times",
        ),
        # CLOSED and OPEN_24_HOURS must NOT have times
        CheckConstraint(
            """
            NOT (
                status != 'OPEN'
                AND (opening_time IS NOT NULL OR closing_time IS NOT NULL)
            )
            """,
            name="ck_non_open_times_null",
        ),
        # Prevent zero-length shifts
        CheckConstraint(
            """
            opening_time IS NULL
            OR closing_time IS NULL
            OR opening_time != closing_time
            """,
            name="ck_no_zero_length_shift",
        ),
        # 24hr must be a single shift (shift_index = 0)
        CheckConstraint(
            """
            NOT (
                status = 'OPEN_24_HOURS'
                AND shift_index != 0
            )
            """,
            name="ck_24hr_single_shift",
        ),
        # Ensure valid day_of_week
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_valid_day_of_week",
        ),
    )


class RestaurantImageType(str, enum.Enum):

    RESTAURANT_PHOTO = "RESTAURANT_PHOTO"
    FOOD_GALLERY = "FOOD_GALLERY"
    DINING_MENU = "DINING_MENU"


class RestaurantImage(Base):

    __tablename__ = "restaurant_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, index=True
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    image_url: Mapped[str] = mapped_column(Text, nullable=False)

    image_type: Mapped[RestaurantImageType] = mapped_column(
        Enum(RestaurantImageType), default=RestaurantImageType.RESTAURANT_PHOTO
    )

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="restaurant_images")

    __table_args__ = (
        Index(
            "unique_primary_per_restaurant",
            "restaurant_id",
            unique=True,
            postgresql_where=(is_primary == True),
        ),
    )


class RestaurantClosure(Base):
    __tablename__ = "restaurant_closures"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    restaurant: Mapped["Restaurant"] = relationship(back_populates="closures")

    __table_args__ = (Index("ix_closure_restaurant_ends", "restaurant_id", "ends_at"),)


# Only used for CuisineType
class CuisineStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    # ARCHIVED = "ARCHIVED"  # a valid Cuisine not in use now
    REVOKED = "REVOKED"


class CuisineType(Base):

    __tablename__ = "cuisine_types"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        index=True,
        default=uuid.uuid4,
    )

    # NOTE: If None then cuisine directly seeded by admin
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    # storing normalized name= name.strip().lower()
    cuisine_name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
    )

    cuisine_slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
    )

    status: Mapped[CuisineStatus] = mapped_column(
        Enum(CuisineStatus),
        default=CuisineStatus.ACTIVE,
    )

    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    revocation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    # relationships

    restaurant_cuisines: Mapped[list[RestaurantCuisineMapping]] = relationship(
        back_populates="cuisine",
    )

    requester: Mapped["User"] = relationship(
        foreign_keys=[requested_by],
        back_populates="approved_created_cuisines",
    )

    approver: Mapped["User"] = relationship(
        "User",
        foreign_keys=[approved_by],
        back_populates="approved_cuisines",
    )

    revoker: Mapped["User"] = relationship(
        "User",
        foreign_keys=[revoked_by],
        back_populates="revoked_cuisines",
    )


# Used for the Mapping model
class MappedCuisineStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PENDING_REVIEW = "PENDING_REVIEW"
    # ARCHIVED = "ARCHIVED"  # a valid Cuisine not in use now
    # REJECTED = "REJECTED"


class RestaurantCuisineMapping(Base):

    __tablename__ = "restaurant_cuisines"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        index=True,
        default=uuid.uuid4,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )

    cuisine_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cuisine_types.id"),
        nullable=True,
    )

    # remove when the cuisine is approved
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cuisine_requests.id"),
        nullable=True,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    status: Mapped[MappedCuisineStatus] = mapped_column(
        Enum(MappedCuisineStatus),
        default=MappedCuisineStatus.PENDING_REVIEW,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # relationship
    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="restaurant_cuisines",
    )
    cuisine: Mapped[CuisineType] = relationship(
        back_populates="restaurant_cuisines",
    )

    __table_args__ = (
        # exactly one must exist:
        # either pending(request_id)
        # or approved(cuisine_id)
        CheckConstraint(
            """
            (
                (cuisine_id IS NOT NULL AND request_id IS NULL)
                OR
                (cuisine_id IS NULL AND request_id IS NOT NULL)
            )
            """,
            name="check_cuisine_or_request_only",
        ),
        # prevent duplicate approved cuisines
        UniqueConstraint(
            "restaurant_id",
            "cuisine_id",
            name="uq_restaurant_cuisine",
        ),
        # prevents duplicate pending cuisine requests
        UniqueConstraint(
            "restaurant_id",
            "request_id",
            name="uq_restaurant_request",
        ),
    )


Index(
    "uq_restaurant_one_primary_cuisine",
    RestaurantCuisineMapping.restaurant_id,
    unique=True,
    postgresql_where=RestaurantCuisineMapping.is_primary.is_(True),
)


# NOTE - only pending requests live here
class CuisineRequest(Base):

    __tablename__ = "cuisine_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        index=True,
        default=uuid.uuid4,
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    cuisine_name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
        unique=True,
    )

    cuisine_slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    requester: Mapped["User"] = relationship(
        foreign_keys=[requested_by],
        back_populates="pending_created_cuisines",
    )


class CuisineRequestHistory(Base):

    __tablename__ = "cuisine_request_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        index=True,
        default=uuid.uuid4,
    )

    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    cuisine_name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
    )

    cuisine_slug: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    # timestamp when request was created originally
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    # timestamp when request was rejected
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    rejection_reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    rejector: Mapped["User"] = relationship(
        foreign_keys=[rejected_by],
        back_populates="rejected_cuisines",
    )

    requester: Mapped["User"] = relationship(
        foreign_keys=[requested_by],
        back_populates="rejected_created_cuisines",
    )
