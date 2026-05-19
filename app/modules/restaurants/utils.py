from slugify import slugify
from sqlalchemy import select

from app.modules.restaurants.models import Restaurant


async def generate_unique_slug(db, name: str) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 1

    while True:
        existing = await db.execute(select(Restaurant).where(Restaurant.slug == slug))
        if not existing.scalar():
            return slug

        slug = f"{base_slug}-{counter}"
        counter += 1
