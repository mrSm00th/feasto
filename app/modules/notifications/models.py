import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class NotificationType(str, enum.Enum):
    # cuisine moderation (existing)
    CUISINE_APPROVED = "CUISINE_APPROVED"
    CUISINE_REJECTED = "CUISINE_REJECTED"
    CUISINE_REVOKED = "CUISINE_REVOKED"

    # order lifecycle — restaurant-facing
    ORDER_PLACED = "ORDER_PLACED"                    # new order arrived

    # order lifecycle — customer-facing
    ORDER_CONFIRMED = "ORDER_CONFIRMED"               # restaurant accepted
    ORDER_PREPARING = "ORDER_PREPARING"               # kitchen started
    ORDER_READY_FOR_PICKUP = "ORDER_READY_FOR_PICKUP" # ready, waiting for rider
    RIDER_ASSIGNED = "RIDER_ASSIGNED"                 # a rider has been locked in
    ORDER_PICKED_UP = "ORDER_PICKED_UP"               # rider has the food
    ORDER_DELIVERED = "ORDER_DELIVERED"               # complete
    ORDER_REJECTED = "ORDER_REJECTED"                 # restaurant declined
    ORDER_CANCELLED = "ORDER_CANCELLED"                # any auto-cancel path

    # rider-facing — distinct from RIDER_ASSIGNED, this is a BROADCAST
    # to candidates before anyone has actually accepted
    NEW_DELIVERY_AVAILABLE = "NEW_DELIVERY_AVAILABLE"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        nullable=False,
        index=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType),
        nullable=False,
    )

    # treating it as a soft reference
    reference_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
        back_populates="notifications",
    )
