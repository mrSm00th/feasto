import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class NotificationType(str, enum.Enum):

    CUISINE_APPROVED = "CUISINE_APPROVED"
    CUISINE_REJECTED = "CUISINE_REJECTED"
    CUISINE_REVOKED = "CUISINE_REVOKED"

    # order lifecycle events
    ORDER_PLACED = "ORDER_PLACED"  # to restaurant owner
    ORDER_CONFIRMED = "ORDER_CONFIRMED"  # to customer
    ORDER_PREPARING = "ORDER_PREPARING"
    ORDER_READY_FOR_PICKUP = "ORDER_READY_FOR_PICKUP"
    RIDER_ASSIGNED = "RIDER_ASSIGNED"
    ORDER_PICKED_UP = "ORDER_PICKED_UP"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_REJECTED = "ORDER_REJECTED"  # to customer
    ORDER_CANCELLED = "ORDER_CANCELLED"  # to customer (auto-cancel)


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
