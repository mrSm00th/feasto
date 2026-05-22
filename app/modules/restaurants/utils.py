import uuid
from io import BytesIO
from math import asin, cos, radians, sin, sqrt

import boto3
from PIL import Image, ImageOps
from slugify import slugify
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
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


MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=(
            settings.s3_access_key_id.get_secret_value()
            if settings.s3_access_key_id
            else None
        ),
        aws_secret_access_key=(
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else None
        ),
        endpoint_url=settings.s3_endpoint_url,
    )


def process_image(content: bytes) -> tuple[bytes, str]:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    with Image.open(BytesIO(content)) as original:
        if original.format not in ALLOWED_FORMATS:
            raise ValueError("Unsupported image format")

        img = ImageOps.exif_transpose(original)

        img = ImageOps.fit(
            img,
            (300, 300),
            method=Image.Resampling.LANCZOS,
        )

        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"

        output = BytesIO()

        img.save(
            output,
            "JPEG",
            quality=85,
            optimize=True,
        )

        output.seek(0)

    return output.read(), filename


def _upload_to_s3(file_bytes: bytes, key: str) -> None:
    s3 = _get_s3_client()
    s3.upload_fileobj(
        BytesIO(file_bytes),
        settings.s3_bucket_name,
        key,
        ExtraArgs={
            "ContentType": "image/jpeg",
            "CacheControl": "max-age=31536000",
        },
    )


def _delete_from_s3(key: str) -> None:
    s3 = _get_s3_client()
    s3.delete_object(Bucket=settings.s3_bucket_name, Key=key)


async def upload_image(file_bytes: bytes, filename: str) -> None:
    key = f"profile_pics/{filename}"
    await run_in_threadpool(_upload_to_s3, file_bytes, key)


async def delete_image(filename: str | None) -> None:
    if filename is None:
        return
    key = f"profile_pics/{filename}"
    await run_in_threadpool(_delete_from_s3, key)
