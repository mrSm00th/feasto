import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class RestaurantEarningStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID_OUT = "PAID_OUT"
    REVERSED = "REVERSED"


class RestaurantPayoutStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RestaurantEarning(Base):

    __tablename__ = "restaurant_earnings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        unique=True,  # one earning row per order
    )

    # Gross figure — item subtotal ONLY. Delivery fee not included
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # 0.1800 = 18.00%

    commission_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # net_amount = gross_amount - commission_amount, computed once at

    status: Mapped[RestaurantEarningStatus] = mapped_column(
        Enum(RestaurantEarningStatus),
        default=RestaurantEarningStatus.PENDING,
        nullable=False,
        index=True,
    )

    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("restaurant_payouts.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Relationships

    restaurant: Mapped["Restaurant"] = relationship(back_populates="earnings")
    order: Mapped["Order"] = relationship()
    payout: Mapped["RestaurantPayout | None"] = relationship(back_populates="earnings")

    __table_args__ = (
        CheckConstraint(
            "gross_amount > 0", name="ck_restaurant_earning_gross_positive"
        ),
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_commission_rate_range",
        ),
        CheckConstraint(
            "net_amount >= 0", name="ck_restaurant_earning_net_non_negative"
        ),
        Index("idx_restaurant_earnings_restaurant_status", "restaurant_id", "status"),
    )


class RestaurantPayout(Base):
    """One batch payment to a restaurant — same shape as Payout for riders."""

    __tablename__ = "restaurant_payouts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # sum of net_amount across all earnings swept into this payout —
    #  what the restaurant actually receives, post-commission

    status: Mapped[RestaurantPayoutStatus] = mapped_column(
        Enum(RestaurantPayoutStatus),
        default=RestaurantPayoutStatus.PENDING,
        nullable=False,
        index=True,
    )

    provider_payout_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )

    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships

    restaurant: Mapped["Restaurant"] = relationship(back_populates="payouts")
    earnings: Mapped[list["RestaurantEarning"]] = relationship(back_populates="payout")

    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_restaurant_payout_total_positive"),
        CheckConstraint(
            "period_end > period_start", name="ck_restaurant_payout_period_valid"
        ),
        UniqueConstraint(
            "restaurant_id",
            "period_start",
            "period_end",
            name="uq_restaurant_payout_restaurant_period",
        ),
    )
