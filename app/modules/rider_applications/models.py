import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class RiderApplicationStatus(str, enum.Enum):
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

    # Identity
    identity_proof_type: Mapped[IdentityProofType] = mapped_column(
        Enum(IdentityProofType),
        nullable=False,
    )

    identity_proof_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    identity_proof_image: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    profile_image: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Vehicle
    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(VehicleType),
        nullable=False,
    )

    vehicle_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    license_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    license_expiry_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    license_image: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Review
    status: Mapped[RiderApplicationStatus] = mapped_column(
        Enum(RiderApplicationStatus),
        default=RiderApplicationStatus.PENDING_REVIEW,
        nullable=False,
        index=True,
    )

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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
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

    __table_args__ = (
        Index(
            "idx_rider_application_applicant_created_at",
            "applicant_id",
            "created_at",
        ),
    )
