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
    Open, fully decode, and validate an image from raw bytes.
    Raises ImageProcessingError for unrecognised or unsupported files.
    Sets the decompression-bomb pixel limit before opening.
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
    JPEG has no transparency support — flatten any alpha channel
    onto a white background. Also converts any other non-RGB mode
    (palette, greyscale) to RGB so img.save(format="JPEG") never fails.
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
    Build a stable, collision-free storage key for any entity's image.
    Callers supply the prefix that describes which entity type and
    access tier this image belongs to.

    Examples:
        _image_key(restaurant_id, filename, "restaurants/covers")
        _image_key(item_id,       filename, "restaurants/menu-items")
        _image_key(application_id, filename, "rider-applications/identity")
    """
    return f"{prefix}/{entity_id}/{filename}"


# Public processing functions


def process_thumbnail(
    content: bytes,
    size: tuple[int, int] = THUMBNAIL_SIZE,
) -> tuple[bytes, str]:
    """
    Validate, crop-to-fill a square, and re-encode as JPEG.

    Use for: restaurant cover photos, food gallery images,
    menu item photos, rider profile photos — anywhere a uniform
    square crop is visually correct and losing the image edges
    doesn't matter.

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
    Validate, downscale to fit within max_size WITHOUT cropping,
    and re-encode as JPEG. Aspect ratio is fully preserved and
    the image is never upscaled.

    Use for: identity proof images, license images, any document
    where cropping could cut off meaningful content (text, photo,
    corners, document number).

    Returns (jpeg_bytes, filename).
    """
    img = _decode_and_validate(content)
    img.thumbnail(max_size, resample=Image.Resampling.LANCZOS)
    img = _normalize_to_rgb(img)
    return _encode_jpeg(img)
