"""(restaurant payout) added models to support restaurant payout

Revision ID: b79fc83e7a6d
Revises: 408878a50a51
Create Date: 2026-06-21 17:06:52.097475

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b79fc83e7a6d"
down_revision: Union[str, Sequence[str], None] = "408878a50a51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


restaurant_earning_status_enum = postgresql.ENUM(
    "PENDING",
    "PAID_OUT",
    "REVERSED",
    name="restaurantearningstatus",
    create_type=False,
)

restaurant_payout_status_enum = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    name="restaurantpayoutstatus",
    create_type=False,
)


def upgrade() -> None:
    # Create enum types once
    restaurant_earning_status_enum.create(op.get_bind(), checkfirst=True)
    restaurant_payout_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "restaurants",
        sa.Column(
            "commission_rate",
            sa.Numeric(5, 4),
            nullable=False,
            server_default="0.1800",
        ),
    )

    op.create_table(
        "restaurant_payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            restaurant_payout_status_enum,
            nullable=False,
        ),
        sa.Column("provider_payout_id", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "total_amount > 0",
            name="ck_restaurant_payout_total_positive",
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="ck_restaurant_payout_period_valid",
        ),
        sa.UniqueConstraint(
            "restaurant_id",
            "period_start",
            "period_end",
            name="uq_restaurant_payout_restaurant_period",
        ),
        sa.UniqueConstraint("provider_payout_id"),
    )

    op.create_index(
        op.f("ix_restaurant_payouts_restaurant_id"),
        "restaurant_payouts",
        ["restaurant_id"],
    )

    op.create_index(
        op.f("ix_restaurant_payouts_status"),
        "restaurant_payouts",
        ["status"],
    )

    op.create_table(
        "restaurant_earnings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("commission_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            restaurant_earning_status_enum,
            nullable=False,
        ),
        sa.Column("payout_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
        ),
        sa.ForeignKeyConstraint(
            ["payout_id"],
            ["restaurant_payouts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "gross_amount > 0",
            name="ck_restaurant_earning_gross_positive",
        ),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1",
            name="ck_commission_rate_range",
        ),
        sa.CheckConstraint(
            "net_amount >= 0",
            name="ck_restaurant_earning_net_non_negative",
        ),
        sa.UniqueConstraint("order_id"),
    )

    op.create_index(
        op.f("ix_restaurant_earnings_restaurant_id"),
        "restaurant_earnings",
        ["restaurant_id"],
    )

    op.create_index(
        op.f("ix_restaurant_earnings_status"),
        "restaurant_earnings",
        ["status"],
    )

    op.create_index(
        op.f("ix_restaurant_earnings_payout_id"),
        "restaurant_earnings",
        ["payout_id"],
    )

    op.create_index(
        "idx_restaurant_earnings_restaurant_status",
        "restaurant_earnings",
        ["restaurant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_restaurant_earnings_restaurant_status",
        table_name="restaurant_earnings",
    )

    op.drop_index(
        op.f("ix_restaurant_earnings_payout_id"),
        table_name="restaurant_earnings",
    )

    op.drop_index(
        op.f("ix_restaurant_earnings_status"),
        table_name="restaurant_earnings",
    )

    op.drop_index(
        op.f("ix_restaurant_earnings_restaurant_id"),
        table_name="restaurant_earnings",
    )

    op.drop_table("restaurant_earnings")

    op.drop_index(
        op.f("ix_restaurant_payouts_status"),
        table_name="restaurant_payouts",
    )

    op.drop_index(
        op.f("ix_restaurant_payouts_restaurant_id"),
        table_name="restaurant_payouts",
    )

    op.drop_table("restaurant_payouts")

    op.drop_column("restaurants", "commission_rate")

    restaurant_payout_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )

    restaurant_earning_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )
