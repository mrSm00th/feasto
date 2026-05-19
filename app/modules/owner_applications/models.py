import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OwnerApplication(Base):
    __tablename__ = "owner_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    applicant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    restaurant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    fssai_license_number: Mapped[str] = mapped_column(
        String(14),
        nullable=False,
        index=True,
        unique=True,
    )

    gst_number: Mapped[str | None] = mapped_column(
        String(15),
        nullable=True,
        index=True,
    )

    # pan_number: Mapped[str] = mapped_column(
    #     String(10),
    #     nullable=False,
    # )

    # bank_account_number: Mapped[str] = mapped_column(
    #     String(50),
    #     nullable=False,
    # )

    status: Mapped["ApplicationStatus"] = mapped_column(
        Enum(ApplicationStatus),
        default=ApplicationStatus.PENDING,
        index=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(Text)

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

    # RELATIONSHIPS

    applicant: Mapped["User"] = relationship(
        "User",
        foreign_keys=[applicant_id],
        back_populates="owner_applications",
    )

    reviewer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[reviewed_by],
        back_populates="reviewed_applications",
    )
