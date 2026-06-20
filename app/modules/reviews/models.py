import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# reviews/models.py


class ReviewerRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    RIDER = "RIDER"


class RevieweeType(str, enum.Enum):
    RIDER = "RIDER"
    RESTAURANT = "RESTAURANT"
    CUSTOMER = "CUSTOMER"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    reviewer_role: Mapped[ReviewerRole] = mapped_column(
        Enum(ReviewerRole), nullable=False, index=True
    )

    reviewee_type: Mapped[RevieweeType] = mapped_column(
        Enum(RevieweeType),
        nullable=False,
        index=True,
    )
    reviewee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        # set when reviewee_type is RIDER or CUSTOMER
    )
    reviewee_restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=True,
        # set when reviewee_type is RESTAURANT
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # relationships

    order: Mapped["Order"] = relationship(back_populates="reviews")

    reviewer: Mapped["User"] = relationship(
        back_populates="reviews_given",
        foreign_keys=[reviewer_id],
    )

    reviewee_user: Mapped["User | None"] = relationship(
        back_populates="reviews_received",
        foreign_keys=[reviewee_user_id],
    )

    reviewee_restaurant: Mapped["Restaurant | None"] = relationship(
        back_populates="reviews",
        foreign_keys=[reviewee_restaurant_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "reviewer_id",
            "reviewee_type",
            name="uq_review_order_reviewer_target",
        ),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        CheckConstraint(
            "(reviewee_type = 'RESTAURANT' AND reviewee_restaurant_id IS NOT NULL AND reviewee_user_id IS NULL) "
            "OR (reviewee_type != 'RESTAURANT' AND reviewee_user_id IS NOT NULL AND reviewee_restaurant_id IS NULL)",
            name="ck_review_exactly_one_target",
        ),
    )
