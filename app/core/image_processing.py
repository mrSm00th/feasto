from __future__ import annotations

import uuid
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.modules.restaurants.models import Restaurant

# Image processing

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
