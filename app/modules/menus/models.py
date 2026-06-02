import enum
import uuid
from datetime import UTC, datetime
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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.modules.restaurants.models import VegType


class MenuItemImageType(str, enum.Enum):
    PRIMARY = "PRIMARY"  # main image shown in UI
    GALLERY = "GALLERY"  # additional images
    THUMBNAIL = "THUMBNAIL"  # small preview (optional)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_categories.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    veg_type: Mapped[VegType] = mapped_column(
        Enum(VegType),
        default=VegType.VEG,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    preparation_time_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    calories: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
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

    # RELATIONSHIP

    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="menu_items",
    )

    category: Mapped["MenuCategory"] = relationship(
        back_populates="menu_items",
    )

    cart_items: Mapped[list["CartItem"]] = relationship(
        back_populates="menu_item",
    )

    order_items: Mapped[list["OrderItem"]] = relationship(
        back_populates="menu_item",
    )


class MenuItemImage(Base):

    __tablename__ = "menu_item_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )

    image_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    image_type: Mapped[MenuItemImageType] = mapped_column(
        Enum(MenuItemImageType),
        default=MenuItemImageType.GALLERY,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    alt_text: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="menu_item_images",
    )


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # optional description
    description: Mapped[str | None] = mapped_column(
        String(350),
        nullable=True,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # RELATIONSHIPS
    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="categories",
    )

    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="category",
    )

    __table_args__ = (
        UniqueConstraint(
            restaurant_id,
            display_order,
        ),
        UniqueConstraint(
            restaurant_id,
            normalized_name,
        ),
    )
