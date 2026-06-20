import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.modules.rider_applications.models import VehicleType


class RiderProfileStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Rider(Base):
    """
    Operational rider profile — created by approve_rider_application()
    when an admin approves a RiderApplication.

    """

    __tablename__ = "riders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # enforcing one rider per user id at db level
        index=True,
    )

    # profile

    profile_image: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        # populated at approval time — key in the public storage bucket
        # under riders/{user_id}/profile.jpg
    )

    # Status

    status: Mapped[RiderProfileStatus] = mapped_column(
        Enum(RiderProfileStatus),
        nullable=False,
        default=RiderProfileStatus.ACTIVE,
        index=True,
    )

    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    suspension_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Rider Availability

    is_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        # True: rider has opened the app and is looking for orders
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Rider's Live location

    current_latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    current_longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    last_location_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        # Used to detect stale location — if now() - last_location_update > 5 min,
        # treat rider as effectively offline even if is_online=True.
    )

    # Vehicle (copied from RiderApplication at approval time)
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        Enum(
            VehicleType,
            name="vehicletype",
            create_type=False,
        ),
        nullable=True,
    )

    vehicle_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Performance counters

    avg_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),  # 0.00 – 5.00, two decimal places
        nullable=False,
        default=Decimal("0.00"),
        # Formula: new_avg = ((old_avg * old_count) + new_rating) / new_count
    )

    total_reviews: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_deliveries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        # Incremented when Order.status transitions to DELIVERED
    )

    # Timestamps

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships

    user: Mapped["User"] = relationship(
        back_populates="rider",
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="rider",
    )

    # Indexes

    __table_args__ = (
        # Composite index for the order-matching query:
        # WHERE is_online = TRUE AND is_available = TRUE
        # Filters most riders out before the geo calculation runs.
        Index(
            "idx_riders_available",
            "is_online",
            "is_available",
        ),
        # Composite index covering both coordinate columns together —
        # individual column indexes are useless for Haversine/bounding-box queries.
        # TODO: migrate to PostGIS GEOGRAPHY column + GIST index for production-scale
        Index(
            "idx_riders_location",
            "current_latitude",
            "current_longitude",
        ),
    )
