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
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.modules.restaurants.models import VegType


class MenuItemImageType(str, enum.Enum):
    PRIMARY = "PRIMARY"  # main image shown in UI
    GALLERY = "GALLERY"  # additional images
    THUMBNAIL = "THUMBNAIL"  # small preview (optional)


class MenuItemStatus(str, enum.Enum):

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


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

    status: Mapped[MenuItemStatus] = mapped_column(
        Enum(MenuItemStatus),
        nullable=False,
        default=MenuItemStatus.ACTIVE,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=1,
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
        nullable=False,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    images: Mapped[list["MenuItemImage"]] = relationship(
        back_populates="menu_item",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "normalized_name",
            name="uq_menu_item_category_normalized_name",
        ),
        UniqueConstraint(
            "category_id",
            "sort_order",
            name="uq_category_id_sort_order",
            deferrable=True,
            initially="DEFERRED",
        ),
    )


class MenuItemImage(Base):

    __tablename__ = "menu_item_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    image_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    image_type: Mapped[MenuItemImageType] = mapped_column(
        Enum(MenuItemImageType, name="menuitemimagetype"),
        nullable=False,
        default=MenuItemImageType.GALLERY,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    alt_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(UTC),
    )

    # RELATIONSHIPS

    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="menu_item_images",
    )

    menu_item: Mapped["MenuItem"] = relationship(
        back_populates="images",
    )

    __table_args__ = (
        # only one PRIMARY image per item
        UniqueConstraint(
            "menu_item_id",
            "image_type",
            name="uq_menu_item_primary_image",
            # partial unique enforced at DB level via a partial index in migration
            # since SQLAlchemy UniqueConstraint can't express WHERE clauses
        ),
        Index(
            "ix_menu_item_images_item_sort",
            "menu_item_id",
            "sort_order",
        ),
    )


class MenuCategoryStatus(str, enum.Enum):

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


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

    status: Mapped[MenuCategoryStatus] = mapped_column(
        Enum(MenuCategoryStatus),
        nullable=False,
        default=MenuCategoryStatus.ACTIVE,
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

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # RELATIONSHIPS
    restaurant: Mapped["Restaurant"] = relationship(
        back_populates="categories",
    )

    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="category",
    )

    __table_args__ = (
        # prevents duplicate sort order for categoris
        UniqueConstraint(
            restaurant_id,
            sort_order,
            deferrable=True,
            initially="DEFERRED",
            name="uq_category_restaurant_id_sort_order",
        ),
        # prevent duplicate categories for a restaurant
        UniqueConstraint(
            restaurant_id,
            normalized_name,
        ),
    )
