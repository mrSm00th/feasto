"""(menu) add deferrable initially deferred constraints for menu ordering

Revision ID: 5f7748b14d08
Revises: d83046f43522
Create Date: 2026-06-08 10:09:38.827953

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f7748b14d08"
down_revision: Union[str, Sequence[str], None] = "d83046f43522"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # auto-generated — correct
    op.drop_constraint(
        op.f("menu_categories_restaurant_id_sort_order_key"),
        "menu_categories",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_category_restaurant_id_sort_order",
        "menu_categories",
        ["restaurant_id", "sort_order"],
        deferrable=True,
        initially="DEFERRED",
    )

    # manually added — menu_items sort_order constraint
    op.drop_constraint("uq_category_id_sort_order", "menu_items", type_="unique")
    op.execute("""
        ALTER TABLE menu_items
        ADD CONSTRAINT uq_category_id_sort_order
        UNIQUE (category_id, sort_order)
        DEFERRABLE INITIALLY DEFERRED
    """)


def downgrade() -> None:
    # menu_items
    op.drop_constraint("uq_category_id_sort_order", "menu_items", type_="unique")
    op.create_unique_constraint(
        "uq_category_id_sort_order",
        "menu_items",
        ["category_id", "sort_order"],
    )

    # auto-generated
    op.drop_constraint(
        "uq_category_restaurant_id_sort_order", "menu_categories", type_="unique"
    )
    op.create_unique_constraint(
        op.f("menu_categories_restaurant_id_sort_order_key"),
        "menu_categories",
        ["restaurant_id", "sort_order"],
        postgresql_nulls_not_distinct=False,
    )
