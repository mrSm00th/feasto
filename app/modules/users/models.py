import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    # PENDING_PARTNER = "PENDING_PARTNER"
    RESTAURANT_OWNER = "RESTAURANT_OWNER"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):

    ACTIVE = "ACTIVE"  # fully usable account
    DEACTIVATED = (
        "DEACTIVATED"  # user deactivaed their account, can be reactivated by user
    )
    SUSPENDED = (
        "SUSPENDED "  # admin level action, can be reactivated by admin after review
    )


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
        index=True,
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

    user_status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus),
        default=UserStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # later add enum for account status like active, suspended, deactivated etc and handle accordingly in the app
    is_account_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # RELATIONSHIPS

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    restaurants: Mapped[list["Restaurant"]] = relationship(
        back_populates="owner",
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
    )

    cart: Mapped[Optional["Cart"]] = relationship(
        back_populates="user",
        uselist=False,
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    partner_applications: Mapped[list["PartnerApplication"]] = relationship(
        back_populates="applicant",
        cascade="all, delete-orphan",
        foreign_keys="[PartnerApplication.applicant_id]",
    )

    reviewed_applications: Mapped[list["PartnerApplication"]] = relationship(
        back_populates="reviewer",
        foreign_keys="[PartnerApplication.reviewed_by]",
    )

    # cuisines requested by the user(RESTAURANT_OWNER)- PENDING
    pending_created_cuisines: Mapped[list["CuisineRequest"]] = relationship(
        back_populates="requester",
        foreign_keys="[CuisineRequest.requested_by]",
    )

    approved_created_cuisines: Mapped[list["CuisineType"]] = relationship(
        back_populates="requester",
        foreign_keys="[CuisineType.requested_by]",
    )

    rejected_created_cuisines: Mapped[list["CuisineRequestHistory"]] = relationship(
        back_populates="requester",
        foreign_keys="[CuisineRequestHistory.requested_by]",
    )

    # cuisines approved by the user(ADMIN)
    approved_cuisines: Mapped[list["CuisineType"]] = relationship(
        back_populates="approver",
        foreign_keys="[CuisineType.approved_by]",
    )

    # cuisines rejected by the user(ADMIN)
    rejected_cuisines: Mapped[list["CuisineRequestHistory"]] = relationship(
        back_populates="rejector",
        foreign_keys="[CuisineRequestHistory.rejected_by]",
    )

    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
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

    user: Mapped["User"] = relationship(
        back_populates="addresses",
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="address",
    )


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

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class NotificationType(str, enum.Enum):

    CUISINE_APPROVED = "CUISINE_APPROVED"
    CUISINE_REJECTED = "CUISINE_REJECTED"


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

    reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cuisine_request_history.id"),
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

    # referencing only the 'Rejected Request'
    reference: Mapped["CuisineRequestHistory"] = relationship(
        foreign_keys=[reference_id],
        back_populates="notifications",
    )
