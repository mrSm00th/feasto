from __future__ import annotations

import uuid
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

# Constants

MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB raw upload cap before processing

# Square crop — restaurant cards, menu item photos, profile photos
THUMBNAIL_SIZE = (800, 800)

# Aspect-preserving resize — identity documents, license images
# Never crops, never upscales, preserves all corners and text
DOCUMENT_MAX_SIZE = (1600, 1600)


class ImageProcessingError(Exception):
    """Raised when uploaded bytes cannot be decoded or are an unsupported format."""


# Private helpers


def _decode_and_validate(content: bytes) -> Image.Image:
    """
    Open and validate an uploaded image.
    """
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    try:
        original = Image.open(BytesIO(content))
        original.load()  # force full decode — surfaces corrupt files early
    except UnidentifiedImageError as exc:
        raise ImageProcessingError("File could not be identified as an image.") from exc

    if original.format not in ALLOWED_FORMATS:
        raise ImageProcessingError(
            f"Unsupported image format: {original.format!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_FORMATS))}"
        )

    # Honour EXIF orientation (portrait-mode phone photos, etc.)
    return ImageOps.exif_transpose(original)


def _normalize_to_rgb(img: Image.Image) -> Image.Image:
    """
    Normalize image modes so the image can be saved as JPEG.
    """
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(
            img,
            mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None,
        )
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _encode_jpeg(img: Image.Image) -> tuple[bytes, str]:
    """
    Re-encode a PIL image as a progressive JPEG with quality 85.
    Returns (jpeg_bytes, uuid_filename).
    """
    filename = f"{uuid.uuid4().hex}.jpg"
    output = BytesIO()
    img.save(output, format="JPEG", quality=85, optimize=True, progressive=True)
    output.seek(0)
    return output.read(), filename


def _image_key(entity_id: uuid.UUID, filename: str, prefix: str) -> str:
    """
    Generate a storage key for an uploaded image.
    """
    return f"{prefix}/{entity_id}/{filename}"


# Public processing functions


def process_thumbnail(
    content: bytes,
    size: tuple[int, int] = THUMBNAIL_SIZE,
) -> tuple[bytes, str]:
    """
    Create a square thumbnail and save it as JPEG.

    Returns (jpeg_bytes, filename).
    """
    img = _decode_and_validate(content)
    img = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)
    img = _normalize_to_rgb(img)
    return _encode_jpeg(img)


def process_document(
    content: bytes,
    max_size: tuple[int, int] = DOCUMENT_MAX_SIZE,
) -> tuple[bytes, str]:
    """
    Resize a document image without cropping.

    Aspect ratio is preserved and the image is never upscaled.

    Returns (jpeg_bytes, filename).
    """
    img = _decode_and_validate(content)
    img.thumbnail(max_size, resample=Image.Resampling.LANCZOS)
    img = _normalize_to_rgb(img)
    return _encode_jpeg(img)
