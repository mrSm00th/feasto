import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.modules.payments.models import PaymentProvider


class OrderStatus(str, enum.Enum):
    AWAITING_PAYMENT = "AWAITING_PAYMENT"  # created, payment not confirmed yet
    PLACED = "PLACED"  # payment confirmed, sent to restaurant
    CONFIRMED = "CONFIRMED"  # restaurant accepted
    PREPARING = "PREPARING"  # kitchen started
    READY_FOR_PICKUP = "READY_FOR_PICKUP"  # ready, waiting for rider
    RIDER_ASSIGNED = "RIDER_ASSIGNED"  # rider accepted the order
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"  # rider picked up
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class CancellationReason(str, enum.Enum):
    PAYMENT_FAILED = "PAYMENT_FAILED"
    RESTAURANT_REJECTED = "RESTAURANT_REJECTED"
    RESTAURANT_TIMEOUT = "RESTAURANT_TIMEOUT"  # auto-cancel after no response
    CUSTOMER_CANCELLED = "CUSTOMER_CANCELLED"
    ITEM_UNAVAILABLE = "ITEM_UNAVAILABLE"
    NO_RIDER_AVAILABLE = "NO_RIDER_AVAILABLE"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class Order(Base):
    # NOTE: intentionally storing duplicate/snapshot data to preserve correct
    # order history even if restaurant name, address, or prices change later.
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=False,
        index=True,
    )

    # currently a place holder
    rider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("riders.id"),
        nullable=True,
        index=True,
    )

    # Snapshots - source of truth for history

    restaurant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # FK kept for joining when address still exists
    address_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("addresses.id"),
        nullable=False,
    )

    # Snapshot — preserved even if user edits or deletes the address later
    delivery_address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    delivery_latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    delivery_longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    # Snapshot contact info at time of order
    customer_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    customer_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    customer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ── Order state ───────────────────────────────────────────────────────

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.AWAITING_PAYMENT,
        nullable=False,
        index=True,
    )

    cancellation_reason: Mapped[CancellationReason | None] = mapped_column(
        Enum(CancellationReason),
        nullable=True,
    )

    cancellation_note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    special_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Financials

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    # Payment (kept as convenience denorm, Payment model is source of truth)

    payment_method: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider),
        nullable=False,
    )

    # ── Timing — one timestamp per status transition ──────────────────────

    # created_at = when order row was created = when checkout was hit
    placed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    preparing_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rider_assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    picked_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Set by restaurant on accept — shown to customer as ETA
    estimated_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    #  Relationships

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    payment: Mapped[Optional["Payment"]] = relationship(
        back_populates="order",
        uselist=False,
    )

    user: Mapped["User"] = relationship(back_populates="orders")

    restaurant: Mapped["Restaurant"] = relationship(back_populates="orders")

    # renamed from 'address' to avoid collision with 'delivery_address' column
    delivery_address_ref: Mapped[Optional["Address"]] = relationship(
        back_populates="orders",
        foreign_keys=[address_id],
    )

    rider: Mapped["Rider"] = relationship(
        back_populates="orders",
        foreign_keys=[rider_id],
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id"),
        nullable=False,
    )

    #  Snapshots
    item_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    item_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    item_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # relationship

    menu_item: Mapped["MenuItem"] = relationship(back_populates="order_items")

    order: Mapped["Order"] = relationship(back_populates="items")
