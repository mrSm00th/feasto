import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class CityStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"  # platform operates here, accepting new applications
    INACTIVE = "INACTIVE"  # not yet launched, or paused


class City(Base):
    __tablename__ = "cities"

    __table_args__ = (UniqueConstraint("name", "state", name="uq_city_name_state"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[CityStatus] = mapped_column(
        Enum(CityStatus),
        default=CityStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    inactivated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    inactivation_reason: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    inactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # relationship

    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by], back_populates="cities_created"
    )

    inactivator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[inactivated_by],
        back_populates="cities_inactivated",
    )
