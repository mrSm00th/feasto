"""(review) updated the model to support review flowr

Revision ID: 8b63d008bd5c
Revises: 652f861236da
Create Date: 2026-06-21 01:06:32.160600

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b63d008bd5c"
down_revision: Union[str, Sequence[str], None] = "652f861236da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("reviews")

    reviewer_role = postgresql.ENUM("CUSTOMER", "RIDER", name="reviewerrole")
    reviewee_type = postgresql.ENUM(
        "RIDER", "RESTAURANT", "CUSTOMER", name="revieweetype"
    )
    # no .create() calls here — op.create_table below will emit
    # CREATE TYPE automatically for each enum column

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_role", reviewer_role, nullable=False),
        sa.Column("reviewee_type", reviewee_type, nullable=False),
        sa.Column("reviewee_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewee_restaurant_id", sa.Uuid(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewee_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewee_restaurant_id"], ["restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "reviewer_id",
            "reviewee_type",
            name="uq_review_order_reviewer_target",
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_review_rating_range"
        ),
        sa.CheckConstraint(
            "(reviewee_type = 'RESTAURANT' AND reviewee_restaurant_id IS NOT NULL AND reviewee_user_id IS NULL) "
            "OR (reviewee_type != 'RESTAURANT' AND reviewee_user_id IS NOT NULL AND reviewee_restaurant_id IS NULL)",
            name="ck_review_exactly_one_target",
        ),
    )
    op.create_index(op.f("ix_reviews_order_id"), "reviews", ["order_id"])
    op.create_index(op.f("ix_reviews_reviewer_role"), "reviews", ["reviewer_role"])
    op.create_index(op.f("ix_reviews_reviewee_type"), "reviews", ["reviewee_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reviews_reviewee_type"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_reviewer_role"), table_name="reviews")
    op.drop_index(op.f("ix_reviews_order_id"), table_name="reviews")
    op.drop_table("reviews")

    postgresql.ENUM(name="reviewerrole").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="revieweetype").drop(op.get_bind(), checkfirst=True)

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "order_id", name="uq_user_order_review"),
    )
    op.create_index(op.f("ix_reviews_id"), "reviews", ["id"])
