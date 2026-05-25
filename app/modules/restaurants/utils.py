import uuid
from io import BytesIO
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from PIL import Image, ImageOps
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


def normalize(text: str) -> str:
    return text.strip().lower()


# The Haversine formula -> distance in meters
def calculate_distance(lat1, lon1, lat2, lon2):
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))

    r = 6371000  # The Radius of earth in meters
    return c * r


RESTAURANT_PICS_DIR = Path("media\restaurant_pics")


def process_restaurant_image(content: bytes) -> str:
    with Image.open(BytesIO(content)) as original:
        img = ImageOps.exif_transpose(original)

        img = ImageOps.fit(img, (300, 300), method=Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = RESTAURANT_PICS_DIR / filename

        RESTAURANT_PICS_DIR.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quality=85, optimize=True)

    return filename


def delete_restaurant_image(filename: str | None) -> None:
    if filename is None:
        return

    filepath = RESTAURANT_PICS_DIR / filename
    if filepath.exists():
        filepath.unlink()
