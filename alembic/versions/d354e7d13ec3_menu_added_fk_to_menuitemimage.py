"""(Menu) added FK to MenuItemImage

Revision ID: d354e7d13ec3
Revises: 78bf7a5b8451
Create Date: 2026-06-08 14:52:43.210966

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d354e7d13ec3"
down_revision: Union[str, Sequence[str], None] = "78bf7a5b8451"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "menu_item_images", sa.Column("menu_item_id", sa.Uuid(), nullable=False)
    )
    op.alter_column(
        "menu_item_images",
        "alt_text",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )
    op.drop_index(op.f("ix_menu_item_images_id"), table_name="menu_item_images")
    op.create_index(
        "ix_menu_item_images_item_sort",
        "menu_item_images",
        ["menu_item_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_menu_item_images_menu_item_id"),
        "menu_item_images",
        ["menu_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_menu_item_images_restaurant_id"),
        "menu_item_images",
        ["restaurant_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_menu_item_primary_image", "menu_item_images", ["menu_item_id", "image_type"]
    )
    op.create_foreign_key(
        None,
        "menu_item_images",
        "menu_items",
        ["menu_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("menu_item_images", "is_primary")
    op.execute("""
        CREATE UNIQUE INDEX uq_menu_item_one_primary_image
        ON menu_item_images (menu_item_id)
        WHERE image_type = 'PRIMARY'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_menu_item_one_primary_image")
    op.add_column(
        "menu_item_images",
        sa.Column("is_primary", sa.BOOLEAN(), autoincrement=False, nullable=False),
    )
    op.drop_constraint(None, "menu_item_images", type_="foreignkey")
    op.drop_constraint("uq_menu_item_primary_image", "menu_item_images", type_="unique")
    op.drop_index(
        op.f("ix_menu_item_images_restaurant_id"), table_name="menu_item_images"
    )
    op.drop_index(
        op.f("ix_menu_item_images_menu_item_id"), table_name="menu_item_images"
    )
    op.drop_index("ix_menu_item_images_item_sort", table_name="menu_item_images")
    op.create_index(
        op.f("ix_menu_item_images_id"), "menu_item_images", ["id"], unique=False
    )
    op.alter_column(
        "menu_item_images",
        "alt_text",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
    op.drop_column("menu_item_images", "menu_item_id")
