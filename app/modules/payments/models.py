import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"  # awaiting payment capture
    PAID = "PAID"
    FAILED = "FAILED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    REFUND_FAILED = "REFUND_FAILED"


class PaymentProvider(str, enum.Enum):
    STRIPE = "STRIPE"
    RAZORPAY = "RAZORPAY"
    COD = "COD"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        unique=True,  # one payment record per order
        index=True,
    )

    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # populated when you create the order with Razorpay/Stripe
    provider_order_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )

    # populated when customer completes payment
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # for webhook signature verification
    provider_signature: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    order: Mapped["Order"] = relationship(back_populates="payment")
