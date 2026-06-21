"""(payment) added enums in paymentstatus to support refund flow

Revision ID: 408878a50a51
Revises: 2ea013a837a3
Create Date: 2026-06-21 15:21:20.145199

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "408878a50a51"
down_revision: Union[str, Sequence[str], None] = "2ea013a837a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ENUM_NAME = "paymentstatus"

OLD_VALUES = ("PENDING", "PAID", "FAILED", "REFUNDED")
NEW_VALUES = (
    "PENDING",
    "PAID",
    "FAILED",
    "REFUND_PENDING",
    "REFUNDED",
    "REFUND_FAILED",
)


def upgrade() -> None:

    op.execute(f"ALTER TYPE {ENUM_NAME} ADD VALUE IF NOT EXISTS 'REFUND_PENDING'")
    op.execute(f"ALTER TYPE {ENUM_NAME} ADD VALUE IF NOT EXISTS 'REFUND_FAILED'")

    op.add_column(
        "payments",
        sa.Column("provider_refund_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_payments_provider_refund_id", "payments", ["provider_refund_id"]
    )

    op.add_column(
        "payments",
        sa.Column("refund_failure_reason", sa.String(length=500), nullable=True),
    )

    op.add_column(
        "payments",
        sa.Column("refund_initiated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:

    op.drop_column("payments", "refund_initiated_at")
    op.drop_column("payments", "refund_failure_reason")
    op.drop_constraint("uq_payments_provider_refund_id", "payments", type_="unique")
    op.drop_column("payments", "provider_refund_id")

    op.execute(f"ALTER TYPE {ENUM_NAME} RENAME TO {ENUM_NAME}_old")

    new_enum = sa.Enum(*OLD_VALUES, name=ENUM_NAME)
    new_enum.create(op.get_bind())

    op.execute(
        f"ALTER TABLE payments "
        f"ALTER COLUMN status TYPE {ENUM_NAME} "
        f"USING status::text::{ENUM_NAME}"
    )

    op.execute(f"DROP TYPE {ENUM_NAME}_old")
