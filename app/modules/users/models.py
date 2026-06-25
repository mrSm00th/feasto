import enum
import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    RESTAURANT_OWNER = "RESTAURANT_OWNER"
    RIDER = "RIDER"
    ADMIN = "ADMIN"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"
    SUSPENDED = "SUSPENDED"


class OTPPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


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

    approved_cuisines: Mapped[list["CuisineType"]] = relationship(
        back_populates="approver",
        foreign_keys="[CuisineType.approved_by]",
    )

    revoked_cuisines: Mapped[list["CuisineType"]] = relationship(
        back_populates="revoker",
        foreign_keys="[CuisineType.revoked_by]",
    )

    rejected_cuisines: Mapped[list["CuisineRequestHistory"]] = relationship(
        back_populates="rejector",
        foreign_keys="[CuisineRequestHistory.rejected_by]",
    )

    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
    )

    rider_applications: Mapped[list["RiderApplication"]] = relationship(
        back_populates="applicant",
        cascade="all, delete-orphan",
        foreign_keys="[RiderApplication.applicant_id]",
    )

    reviewed_rider_applications: Mapped[list["RiderApplication"]] = relationship(
        back_populates="reviewer",
        foreign_keys="[RiderApplication.reviewed_by]",
    )

    cities_created: Mapped[list["City"]] = relationship(
        back_populates="creator",
        foreign_keys="[City.created_by]",
    )

    cities_inactivated: Mapped[list["City"]] = relationship(
        back_populates="inactivator",
        foreign_keys="[City.inactivated_by]",
    )

    rider: Mapped[Optional["Rider"]] = relationship(
        back_populates="user",
        uselist=False,
    )

    reviews_given: Mapped[list["Review"]] = relationship(
        back_populates="reviewer",
        foreign_keys="[Review.reviewer_id]",
    )

    reviews_received: Mapped[list["Review"]] = relationship(
        back_populates="reviewee_user",
        foreign_keys="[Review.reviewee_user_id]",
    )

    otp_verifications: Mapped[list["OTPVerification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
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


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

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

    # never store plaintext — stores hashed OTP or hashed reset token
    otp_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    purpose: Mapped[OTPPurpose] = mapped_column(
        Enum(OTPPurpose),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    user: Mapped["User"] = relationship(back_populates="otp_verifications")

    __table_args__ = (Index("ix_otp_user_purpose", "user_id", "purpose"),)
