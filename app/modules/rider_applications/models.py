import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class RiderApplicationStatus(str, enum.Enum):
    CITY_ADDED = "CITY_ADDED"
    IDENTITY_PROOF_ADDED = "IDENTITY_PROOF_ADDED"
    PROFILE_IMAGE_ADDED = "PROFILE_IMAGE_ADDED"
    VEHICLE_DETAILS_ADDED = "VEHICLE_DETAILS_ADDED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class IdentityProofType(str, enum.Enum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"


class VehicleType(str, enum.Enum):
    BIKE_SCOOTER = "BIKE_SCOOTER"
    EV = "EV"


class RiderApplication(Base):
    __tablename__ = "rider_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[RiderApplicationStatus] = mapped_column(
        Enum(RiderApplicationStatus),
        default=RiderApplicationStatus.CITY_ADDED,
        nullable=False,
        index=True,
    )

    # Step 1 — city, only field guaranteed present from row creation
    city_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cities.id"),
        nullable=False,
    )

    # Identity
    identity_proof_type: Mapped[IdentityProofType | None] = mapped_column(
        Enum(IdentityProofType),
        nullable=True,
    )

    identity_proof_number: Mapped[str | None] = mapped_column(
        String(512),  # encrypted
        nullable=True,
    )

    identity_proof_image: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    profile_image: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Vehicle
    vehicle_type: Mapped[VehicleType | None] = mapped_column(
        Enum(VehicleType),
        nullable=True,
    )

    vehicle_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    license_number: Mapped[str | None] = mapped_column(
        String(512),  # encrypted
        nullable=True,
    )

    license_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    license_image: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Review
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    # Relationships
    applicant: Mapped["User"] = relationship(
        "User",
        foreign_keys=[applicant_id],
        back_populates="rider_applications",
    )

    reviewer: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="reviewed_rider_applications",
    )

    city: Mapped["City"] = relationship()

    __table_args__ = (
        Index(
            "idx_rider_application_applicant_created_at",
            "applicant_id",
            "created_at",
        ),
        Index(
            "uq_rider_applications_active_per_user",
            "applicant_id",
            unique=True,
            postgresql_where=text("status NOT IN ('APPROVED', 'REJECTED')"),
        ),
    )
