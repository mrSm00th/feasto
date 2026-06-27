"""
Storage backend abstraction.

Two access tiers, each its own bucket (or local folder in dev):
    public  — menu images, restaurant photos, rider profile photos.
               Anyone with the URL can view. No auth needed.
    private — identity proofs, license images, KYC documents.
               Never publicly readable. Access only via short-lived
               signed URLs generated on demand for authorized requests.

Switch backends via STORAGE_BACKEND=local | s3 in .env.
Default is local so no extra config is needed during development.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

logger = logging.getLogger(__name__)


# Abstract interface


class StorageBackend(ABC):

    @abstractmethod
    async def upload(
        self, file_bytes: bytes, key: str, content_type: str = "image/jpeg"
    ) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def public_url(self, key: str) -> str: ...

    @abstractmethod
    async def generate_signed_url(self, key: str, expires_in: int = 300) -> str: ...


# Local filesystem (dev & tests)


class LocalStorage(StorageBackend):
    """
    Local storage backend used for development.
    """

    def __init__(self, base_dir: Path, url_prefix: str) -> None:
        self.base_dir = base_dir
        self.url_prefix = url_prefix.rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _abs(self, key: str) -> Path:
        dest = (self.base_dir / key).resolve()
        if not dest.is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Unsafe storage key: {key!r}")
        return dest

    def _write(self, dest: Path, data: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _unlink(self, dest: Path) -> None:
        if dest.exists():
            dest.unlink()

    async def upload(
        self, file_bytes: bytes, key: str, content_type: str = "image/jpeg"
    ) -> None:
        dest = self._abs(key)
        await run_in_threadpool(self._write, dest, file_bytes)
        logger.debug("LocalStorage: wrote %s (%d bytes)", dest, len(file_bytes))

    async def delete(self, key: str) -> None:
        dest = self._abs(key)
        await run_in_threadpool(self._unlink, dest)
        logger.debug("LocalStorage: deleted %s", dest)

    def public_url(self, key: str) -> str:
        return f"{self.url_prefix}/{key}"

    async def generate_signed_url(self, key: str, expires_in: int = 300) -> str:
        # No real signing in dev — return the normal URL.
        return self.public_url(key)


#  AWS S3 / S3-compatible (for production)


class S3Storage(StorageBackend):

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket
        self._region: str = settings.s3_region
        self._endpoint: str | None = settings.s3_endpoint_url
        # build once, reuse — not per-call
        self._client = boto3.client(
            "s3",
            region_name=self._region,
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
            endpoint_url=self._endpoint,
        )

    def _upload_sync(self, file_bytes: bytes, key: str, content_type: str) -> None:
        self._client.upload_fileobj(
            BytesIO(file_bytes),
            self._bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "max-age=31536000, immutable",
            },
        )

    def _delete_sync(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError):
            logger.warning("S3Storage: could not delete key %r", key, exc_info=True)

    def _generate_signed_url_sync(self, key: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def upload(
        self, file_bytes: bytes, key: str, content_type: str = "image/jpeg"
    ) -> None:
        await run_in_threadpool(self._upload_sync, file_bytes, key, content_type)

    async def delete(self, key: str) -> None:
        await run_in_threadpool(self._delete_sync, key)

    def public_url(self, key: str) -> str:
        if self._endpoint:
            # Supabase public URL format
            # https://<project-ref>.supabase.co/storage/v1/object/public/<bucket>/<key>
            base = self._endpoint.replace("/storage/v1/s3", "")
            return f"{base}/storage/v1/object/public/{self._bucket}/{key}"
        # standard S3
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    async def generate_signed_url(self, key: str, expires_in: int = 300) -> str:
        return await run_in_threadpool(self._generate_signed_url_sync, key, expires_in)


def get_public_storage() -> StorageBackend:

    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3Storage(bucket=settings.s3_public_bucket_name)
    return LocalStorage(
        base_dir=Path("media/public"),
        url_prefix="/media/public",
    )


def get_private_storage() -> StorageBackend:
    """
    Returns the private storage backend.
    """
    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3Storage(bucket=settings.s3_private_bucket_name)
    return LocalStorage(
        base_dir=Path("media/private"),
        url_prefix="/media/private",
    )


def get_storage() -> StorageBackend:
    """
    Returns the default storage backend.
    """
    return get_public_storage()


# ── Shared upload helper ──────────────────────────────────────────────────


async def upload_processed_image(
    storage: StorageBackend,
    file_bytes: bytes,
    key: str,
) -> None:
    """
    Upload processed image bytes and handle storage errors.
    """
    from fastapi import HTTPException

    try:
        await storage.upload(file_bytes, key, content_type="image/jpeg")
    except Exception as exc:
        logger.exception("Storage upload failed for key %r", key)
        raise HTTPException(
            status_code=502,
            detail="Image upload to storage failed. Please try again.",
        ) from exc


# Cleanup helper


async def _cleanup_keys(storage: StorageBackend, keys: list[str]) -> None:
    """
    Best-effort cleanup for uploaded files.
    """
    results = await asyncio.gather(
        *[storage.delete(k) for k in keys],
        return_exceptions=True,
    )
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("Cleanup failed for key %r: %s", key, result)
