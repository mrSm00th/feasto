import enum
import uuid
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


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
    INCOMPLETE = "INCOMPLETE"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ImageType(str, enum.Enum):
    BANNER = "BANNER"
    LOGO = "LOGO"
    GALLERY = "GALLERY"
    THUMBNAIL = "THUMBNAIL"


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

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    fssai_license_number: Mapped[str] = mapped_column(
        String(14),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    address_line_1: Mapped[str] = mapped_column(
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

    opening_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    closing_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
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
        default=RestaurantStatus.INCOMPLETE,
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

    categories: Mapped[list["Category"]] = relationship(
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

    orders: Mapped[list["Order"]] = relationship(
        back_populates="restaurant",
    )

    availability: Mapped[list["RestaurantAvailability"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )


class RestaurantAvailability(Base):

    __tablename__ = "restaurant_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, index=True
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day_of_week: Mapped[DayOfWeek] = mapped_column(
        Enum(DayOfWeek),
        nullable=False,
    )

    opening_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    closing_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    is_closed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="availability")


class RestaurantImage(Base):

    __tablename__ = "restaurant_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, index=True
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_type: Mapped[ImageType] = mapped_column(
        Enum(ImageType), default=ImageType.GALLERY
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    alt_text: Mapped[str] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="restaurant_images")
