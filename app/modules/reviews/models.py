import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=False,
    )

    # reviewed after delivery
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )

    # 1-5
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # relationships
    user: Mapped["User"] = relationship(
        back_populates="reviews",
        foreign_keys="[Review.user_id]",
    )

    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="reviews", foreign_keys="[Review.restaurant_id]"
    )

    __table_args__ = (
        # Ensure a user can only review an order once
        UniqueConstraint("user_id", "order_id", name="uq_user_order_review"),
    )
