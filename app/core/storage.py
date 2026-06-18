"""
Storage backend abstraction.

Applying Two access tiers, each with its own bucket (/or local folder in dev phase):
    - public  : menu images, restaurant photos, rider profile photos —
                anyone with the URL can view, no auth needed
    - private : identity proofs, license images, KYC documents —
                never publicly readable; access only via short-lived
                signed URLs generated on demand for authorized requests

Switching backends between dev/production via STORAGE_BACKEND=local | s3 in .env.
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


#  Abstract interface


class StorageBackend(ABC):
    """Blueprint every storage backend must implement."""

    @abstractmethod
    async def upload(
        self, file_bytes: bytes, key: str, content_type: str = "image/jpeg"
    ) -> None:
        """Upload bytes to the given key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the object at key."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Return a permanently-accessible URL. Only meaningful for public backends."""

    @abstractmethod
    async def generate_signed_url(self, key: str, expires_in: int = 300) -> str:
        """Return a temporary URL valid for `expires_in` seconds."""


# Local filesystem (for dev & tests)


class LocalStorage(StorageBackend):
    """
    Local-disk backend. No real access control exists for local dev —
    signed URLs so, simply return the same path as public_url, since there's

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
        return self.public_url(key)


# AWS S3 (or any S3 style bucket storage for production)


class S3Storage(StorageBackend):
    """
    S3-compatible backend. `bucket` is passed explicitly by the caller —
    a single S3Storage instance always targets one specific bucket, so
    the public/private split happens at construction time via the
    factory functions below, not inside this class.
    """

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket
        self._region: str = settings.s3_region
        self._endpoint: str | None = settings.s3_endpoint_url

    def _client(self):
        return boto3.client(
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
        self._client().upload_fileobj(
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
            self._client().delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError):
            logger.warning("S3Storage: could not delete key %r", key, exc_info=True)

    def _generate_signed_url_sync(self, key: str, expires_in: int) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def upload(
        self, file_bytes: bytes, key: str, content_type: str = "image/jpeg"
    ) -> None:
        await run_in_threadpool(self._upload_sync, file_bytes, key, content_type)
        logger.debug("S3Storage: uploaded s3://%s/%s", self._bucket, key)

    async def delete(self, key: str) -> None:
        await run_in_threadpool(self._delete_sync, key)
        logger.debug("S3Storage: deleted s3://%s/%s", self._bucket, key)

    def public_url(self, key: str) -> str:
        if self._endpoint:
            return f"{self._endpoint.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"

    async def generate_signed_url(self, key: str, expires_in: int = 300) -> str:
        return await run_in_threadpool(self._generate_signed_url_sync, key, expires_in)


# Factories


def get_public_storage() -> StorageBackend:
    """
    For content shown to any user: menu images, restaurant photos,
    rider profile photos.
    """
    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3Storage(bucket=settings.s3_public_bucket_name)
    return LocalStorage(base_dir=Path("media/public"), url_prefix="/media/public")


def get_private_storage() -> StorageBackend:
    """
    For sensitive documents: identity proofs, license images.
    Never publicly readable — only accessed via generate_signed_url().
    """
    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3Storage(bucket=settings.s3_private_bucket_name)
    return LocalStorage(base_dir=Path("media/private"), url_prefix="/media/private")


async def _cleanup_keys(storage: StorageBackend, keys: list[str]) -> None:
    """Delete storage objects without raising — used in error-recovery paths."""
    results = await asyncio.gather(
        *[storage.delete(k) for k in keys],
        return_exceptions=True,
    )
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("Cleanup failed for key %r: %s", key, result)
