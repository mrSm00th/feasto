from __future__ import annotations

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
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    RESTURANT_OWNER = "RESTAURANT_OWNER"
    ADMIN = "ADMIN"


class VegType(str, enum.Enum):
    VEG = "VEG"
    MIXED = "MIXED"
    NON_VEG = "NON_VEG"


class ImageType(str, enum.Enum):
    BANNER = "BANNER"
    LOGO = "LOGO"
    GALLERY = "GALLERY"
    THUMBNAIL = "THUMBNAIL"


class OrderStatus(str, enum.Enum):
    PLACED = "PLACED"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentProvider(str, enum.Enum):
    STRIPE = "STRIPE"
    RAZORPAY = "RAZORPAY"
    COD = "COD"


class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DayOfWeek(str, Enum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
    )

    phone_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.CUSTOMER,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    is_verified: Mapped[bool] = mapped_column(
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

    # RELATIONSHIPS

    addresses: Mapped[list[Address]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    restaurants: Mapped[list[Restaurant]] = relationship(
        back_populates="owner",
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="user",
    )

    cart: Mapped[Cart | None] = relationship(
        back_populates="user",
        uselist=False,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    owner_applications: Mapped[list["OwnerApplication"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    address_line_1: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    address_line_2: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    postal_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    is_default: Mapped[bool] = mapped_column(
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

    # RELATIONSHIP

    user: Mapped[User] = relationship(
        back_populates="addresses",
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="address",
    )


# OWNER APPLICATION MODEL


class OwnerApplication(Base):
    __tablename__ = "owner_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    restaurant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    fssai_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    gst_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    pan_masked: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    bank_masked: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus),
        default=ApplicationStatus.PENDING,
        index=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(Text)

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    # RELATIONSHIPS

    user: Mapped["User"] = relationship(
        back_populates="owner_applications",
    )


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    cuisine_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    veg_type: Mapped[VegType] = mapped_column(
        VegType,
        default=VegType.VEG,
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    opening_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    closing_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # when the owner temporarily closes the restaurant for the day or for a specific period
    # they can set this flag to true. This will help in hiding the restaurant from the customers during that period.
    is_manually_closed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    avg_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        default=0,
    )

    total_reviews: Mapped[int] = mapped_column(
        Integer,
        default=0,
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

    # relationships
    owner: Mapped[User] = relationship(
        back_populates="restaurants",
    )

    categories: Mapped[list[Category]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    menu_items: Mapped[list[MenuItem]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    images: Mapped[list[RestaurantImage]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="restaurant",
    )

    availability: Mapped[list[RestaurantAvailability]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )


class RestaurantAvailability(Base):

    __tablename__ = "restaurant_availability"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, index=True
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day_of_week: Mapped[DayOfWeek] = mapped_column(
        Enum(DayOfWeek),
        nullable=False,
    )

    opening_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    closing_time: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    is_closed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="availability")


class RestaurantImage(Base):

    __tablename__ = "restaurant_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, index=True
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_type: Mapped[ImageType] = mapped_column(ImageType, default=ImageType.GALLERY)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    alt_text: Mapped[str | None] = mapped_column(String(255), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="images")


class Category(Base):
    __tablename__ = "categories"

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

    description: Mapped[str | None] = mapped_column(
        Text,
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
    restaurant: Mapped[Restaurant] = relationship(
        back_populates="categories",
    )

    menu_items: Mapped[list[MenuItem]] = relationship(
        back_populates="category",
    )


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
        ForeignKey("categories.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
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

    is_vegetarian: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    restaurant: Mapped[Restaurant] = relationship(
        back_populates="menu_items",
    )

    category: Mapped[Category] = relationship(
        back_populates="menu_items",
    )

    cart_items: Mapped[list[CartItem]] = relationship(
        back_populates="menu_item",
    )

    order_items: Mapped[list[OrderItem]] = relationship(
        back_populates="menu_item",
    )


class Cart(Base):

    __tablename__ = "carts"

    # NOTE - one cart per user only
    # cart will hold the items from a single restaurant only

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id"),
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=0,
        nullable=False,
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

    # RELATIONSHIPS

    user: Mapped[User] = relationship(back_populates="cart")

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart",
        cascade="all,delete-orphan",
    )


class CartItem(Base):

    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("menu_items.id"),
        nullable=False,
        index=True,
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


class Order(Base):

    # NOTE- intentionally storing duplicate data to maintain correct order history
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
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

    restaurant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    address_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("addresses.id"),
        nullable=False,
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        default=OrderStatus.PLACED,
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus),
        default=PaymentStatus.PENDING,
    )

    payment_method: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider),
    )

    special_instructions: Mapped[str | None] = mapped_column(Text)

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    payment: Mapped[Payment | None] = relationship(
        back_populates="order",
        uselist=False,
    )

    user = relationship(
        "User",
        back_populates="orders",
    )
    restaurant = relationship(
        "Restaurant",
        back_populates="orders",
    )
    address = relationship(
        "Address",
        back_populates="orders",
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

    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    item_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    menu_item: Mapped[MenuItem] = relationship(back_populates="order_items")
    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
        nullable=False,
    )

    payment_provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider),
        nullable=False,
    )

    transaction_id: Mapped[str | None] = mapped_column(String(255))

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus),
        default=PaymentStatus.PENDING,
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    order: Mapped[Order] = relationship(back_populates="payment")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token: Mapped[str] = mapped_column(Text, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
