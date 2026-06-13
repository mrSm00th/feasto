import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        unique=True,  # enforces one cart per user at DB level
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=False,
    )

    # DROP total_amount — compute it, don't store it
    # @property or compute in schema from items

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

    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
    )
    user: Mapped["User"] = relationship(back_populates="cart")

    restaurant: Mapped["Restaurant"] = relationship()


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id"),
        nullable=False,
    )

    item_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )  # ADD THIS — snapshot at add time

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    item_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )  # snapshot at add time

    # total_price is quantity * item_price — derive it, don't store it

    # UniqueConstraint so a user can't have duplicate rows for the same menu item
    __table_args__ = (
        UniqueConstraint(
            "cart_id",
            "menu_item_id",
            name="uq_cart_menu_item",
        ),
    )

    menu_item: Mapped["MenuItem"] = relationship()

    cart: Mapped["Cart"] = relationship(
        back_populates="items",
        lazy="raise",
    )
