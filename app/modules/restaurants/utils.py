# import uuid
# from io import BytesIO
# from math import asin, cos, radians, sin, sqrt

# import boto3
# from PIL import Image, ImageOps
# from slugify import slugify
# from sqlalchemy import select
# from starlette.concurrency import run_in_threadpool

# from app.core.config import settings
# from app.modules.restaurants.models import Restaurant


# async def generate_unique_slug(db, name: str) -> str:
#     base_slug = slugify(name)

#     result = await db.execute(
#         select(Restaurant.slug).where(Restaurant.slug.like(f"{base_slug}%"))
#     )
#     existing_slugs = {row[0] for row in result.all()}

#     if base_slug not in existing_slugs:
#         return base_slug

#     counter = 1
#     while f"{base_slug}-{counter}" in existing_slugs:
#         counter += 1

#     return f"{base_slug}-{counter}"


# def normalize(text: str) -> str:
#     return text.strip().lower()


# # The Haversine formula -> distance in meters
# def calculate_distance(lat1, lon1, lat2, lon2):
#     # convert decimal degrees to radians
#     lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

#     dlon = lon2 - lon1
#     dlat = lat2 - lat1

#     a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
#     c = 2 * asin(sqrt(a))

#     r = 6371000  # The Radius of earth in meters
#     return c * r


# MAX_IMAGE_PIXELS = 20_000_000
# ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


# def _get_s3_client():
#     return boto3.client(
#         "s3",
#         region_name=settings.s3_region,
#         aws_access_key_id=(
#             settings.s3_access_key_id.get_secret_value()
#             if settings.s3_access_key_id
#             else None
#         ),
#         aws_secret_access_key=(
#             settings.s3_secret_access_key.get_secret_value()
#             if settings.s3_secret_access_key
#             else None
#         ),
#         endpoint_url=settings.s3_endpoint_url,
#     )


# def process_image(content: bytes) -> tuple[bytes, str]:
#     Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

#     with Image.open(BytesIO(content)) as original:
#         if original.format not in ALLOWED_FORMATS:
#             raise ValueError("Unsupported image format")

#         img = ImageOps.exif_transpose(original)

#         img = ImageOps.fit(
#             img,
#             (300, 300),
#             method=Image.Resampling.LANCZOS,
#         )

#         if img.mode in ("RGBA", "LA", "P"):
#             img = img.convert("RGB")

#         filename = f"{uuid.uuid4().hex}.jpg"

#         output = BytesIO()

#         img.save(
#             output,
#             "JPEG",
#             quality=85,
#             optimize=True,
#         )

#         output.seek(0)

#     return output.read(), filename


# def _upload_to_s3(file_bytes: bytes, key: str) -> None:
#     s3 = _get_s3_client()
#     s3.upload_fileobj(
#         BytesIO(file_bytes),
#         settings.s3_bucket_name,
#         key,
#         ExtraArgs={
#             "ContentType": "image/jpeg",
#             "CacheControl": "max-age=31536000",
#         },
#     )


# def _delete_from_s3(key: str) -> None:
#     s3 = _get_s3_client()
#     s3.delete_object(Bucket=settings.s3_bucket_name, Key=key)


# async def upload_image(file_bytes: bytes, filename: str) -> None:
#     key = f"profile_pics/{filename}"
#     await run_in_threadpool(_upload_to_s3, file_bytes, key)


# async def delete_image(filename: str | None) -> None:
#     if filename is None:
#         return
#     key = f"profile_pics/{filename}"
#     await run_in_threadpool(_delete_from_s3, key)


"""
Restaurant utility helpers.

Image processing lives here; storage I/O lives in storage.py.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from io import BytesIO
from math import asin, cos, radians, sin, sqrt

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.restaurants.models import Restaurant

# ──────────────────────────────────────────────────────────────────────────────
# Text helpers
# ──────────────────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    return text.strip().lower()


# ──────────────────────────────────────────────────────────────────────────────
# Slug generation
# ──────────────────────────────────────────────────────────────────────────────

# utils.py — drop-in replacement for generate_unique_slug


async def generate_unique_slug(db: AsyncSession, name: str, city: str) -> str:
    """
    Produce a URL-safe slug in the form  {name}-{city}  or
    {name}-{city}-{n}  (n ≥ 2) if a collision exists.

    The LIKE pre-filter keeps the query fast; the regex post-filter
    ensures we only count exact variants, not unrelated restaurants
    whose slug happens to share the same prefix.
    """
    base_slug = slugify(f"{name} {city}")

    # Only fetch slugs that are this base or could be numbered variants of it
    candidate_pattern = re.compile(rf"^{re.escape(base_slug)}(-\d+)?$")

    result = await db.execute(
        select(Restaurant.slug).where(Restaurant.slug.like(f"{base_slug}%"))
    )
    existing = {row[0] for row in result.all() if candidate_pattern.match(row[0])}

    if base_slug not in existing:
        return base_slug

    # Start at 2 so the series reads:
    #   mcdonalds-mumbai  →  mcdonalds-mumbai-2  →  mcdonalds-mumbai-3
    counter = 2
    while f"{base_slug}-{counter}" in existing:
        counter += 1

    return f"{base_slug}-{counter}"


# ──────────────────────────────────────────────────────────────────────────────
# Geo distance  (Haversine)
# ──────────────────────────────────────────────────────────────────────────────


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the distance in metres between two (lat, lon) points."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6_371_000  # Earth radius in metres


# ──────────────────────────────────────────────────────────────────────────────
# Image processing
# ──────────────────────────────────────────────────────────────────────────────

# Pillow hard-limits to avoid decompression-bomb attacks
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Output dimensions — square thumbnail suitable for restaurant cards
OUTPUT_SIZE = (800, 800)


class ImageProcessingError(Exception):
    """Raised when the uploaded bytes cannot be decoded or are an unsupported format."""


def process_image(content: bytes) -> tuple[bytes, str]:
    """
    Validate, resize, and re-encode *content* as a JPEG.

    Returns
    -------
    (jpeg_bytes, filename)
        *filename* is a UUID-based string like ``"a1b2c3d4…ef.jpg"`` that the
        caller should use as the storage key suffix.

    Raises
    ------
    ImageProcessingError
        If the bytes are not a recognisable image or are in an unsupported format.
    """
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    try:
        with Image.open(BytesIO(content)) as original:
            if original.format not in ALLOWED_FORMATS:
                raise ImageProcessingError(
                    f"Unsupported image format: {original.format!r}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_FORMATS))}"
                )

            # Honour EXIF orientation (e.g. photos taken in portrait mode)
            img = ImageOps.exif_transpose(original)

            # Crop-to-fit so the thumbnail is always square with no letterboxing
            img = ImageOps.fit(
                img,
                OUTPUT_SIZE,
                method=Image.Resampling.LANCZOS,
            )

            # JPEG does not support transparency — flatten to white background
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(
                    img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
                )
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            filename = f"{uuid.uuid4().hex}.jpg"

            output = BytesIO()
            img.save(output, format="JPEG", quality=85, optimize=True, progressive=True)
            output.seek(0)

        return output.read(), filename

    except UnidentifiedImageError as exc:
        raise ImageProcessingError("File could not be identified as an image.") from exc


def _get_upsert_fn():
    """
    Return the dialect-specific `insert` function.
    Centralised here so every route stays dialect-agnostic.
    Switch from SQLite to PostgreSQL by changing DATABASE_URL — no route changes.
    """
    db_url: str = settings.database_url
    if db_url.startswith("postgresql"):
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


async def _get_owned_restaurant(
    restaurant_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> Restaurant:
    """
    Fetch a restaurant and verify ownership in one query.
    Raises 404 for both "not found" and "not owned" — avoids leaking
    the existence of restaurants owned by others.
    """
    restaurant = await db.scalar(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == owner_id,
        )
    )
    if not restaurant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found.",
        )
    return restaurant


def _build_availability_rows(
    restaurant_id: uuid.UUID,
    shifts: list,
) -> list[dict]:
    """Convert validated schema entries into dicts for bulk upsert."""
    return [
        {
            "id": uuid.uuid4(),
            "restaurant_id": restaurant_id,
            "day_of_week": entry.day_of_week,
            "status": entry.status,
            "opening_time": entry.opening_time,
            "closing_time": entry.closing_time,
            "shift_index": entry.shift_index,
        }
        for entry in shifts
    ]


# =====================
# noramize cuisine name
# =====================


def normalize_cuisine_name(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("Cuisine name cannot be empty")

    # normalize the cuisine name
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    name = name.lower()

    # Standardizing the  connectors
    name = re.sub(r"\s*(&|\+|/)\s*", " and ", name)

    # Replacing the separators
    name = re.sub(r"[-_]+", " ", name)

    # Remove special chars
    name = re.sub(r"[^a-z0-9 ]+", "", name)

    # Collapse spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name.title()


def slugify(value: str) -> str:

    # Normalize unicode characters (é -> e)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")

    value = value.lower()

    # Replacing all  non-alphanumeric chars with hyphen
    value = re.sub(r"[^a-z0-9]+", "-", value)

    # Removing any  leading/trailing hyphens
    value = value.strip("-")

    return value
