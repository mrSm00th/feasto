"""
Storage backend abstraction.

Switch between local filesystem (dev/test) and S3 (production)
by setting  STORAGE_BACKEND=local | s3  in your .env & config file.

Local backend
-------------
Files are written to  <MEDIA_ROOT>/<key>  on disk.

S3 backend
----------
Files are uploaded to  s3://<bucket>/<key>.
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


# Base


# Abstract class
class StorageBackend(ABC):
    """Abstract Class acts as the blue print"""

    @abstractmethod
    async def upload(self, file_bytes: bytes, key: str) -> None:
        """Abstract function implemented by the inheriting class"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Function used to Delete the object at key."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Return the URL used by client to retrieve the object."""


# Local filesystem  (for dev & tests)


MEDIA_ROOT = Path("media")


class LocalStorage(StorageBackend):
    """
    handles file uploads to the local system for development and testing.
    """

    def __init__(
        self,
        base_dir: Path = MEDIA_ROOT,
        url_prefix: str = "/media",
    ) -> None:
        self.base_dir = base_dir
        self.url_prefix = url_prefix.rstrip("/")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # helper functions

    def _abs(self, key: str) -> Path:
        dest = (self.base_dir / key).resolve()
        # prevention against traversal attacks
        if not dest.is_relative_to(self.base_dir.resolve()):
            raise ValueError(f"Unsafe storage key: {key!r}")
        return dest

    def _write(self, dest: Path, data: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def _unlink(self, dest: Path) -> None:
        if dest.exists():
            dest.unlink()

    # interface functions

    async def upload(self, file_bytes: bytes, key: str) -> None:
        dest = self._abs(key)
        await run_in_threadpool(self._write, dest, file_bytes)
        logger.debug("LocalStorage: wrote %s (%d bytes)", dest, len(file_bytes))

    async def delete(self, key: str) -> None:
        dest = self._abs(key)
        await run_in_threadpool(self._unlink, dest)
        logger.debug("LocalStorage: deleted %s", dest)

    def public_url(self, key: str) -> str:
        return f"{self.url_prefix}/{key}"


# AWS S3  (production / staging)


class S3Storage(StorageBackend):
    """
    Handles Uploads to S3-compatible object storage (AWS S3, MinIO, localstack).

    Objects are stored with:
        Content-Type : image/jpeg
        Cache-Control: max-age=31536000, immutable
        ACL          : private  (serve through CloudFront / signed URLs if needed)
    """

    def __init__(self) -> None:
        self._bucket: str = settings.s3_bucket_name
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

    # sync helpers run in a thread pool

    def _upload_sync(self, file_bytes: bytes, key: str) -> None:
        self._client().upload_fileobj(
            BytesIO(file_bytes),
            self._bucket,
            key,
            ExtraArgs={
                "ContentType": "image/jpeg",
                "CacheControl": "max-age=31536000, immutable",
            },
        )

    def _delete_sync(self, key: str) -> None:
        try:
            self._client().delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError):
            # Logging but not raising as - a missing object is not a fatal error
            logger.warning("S3Storage: could not delete key %r", key, exc_info=True)

    # interface
    async def upload(self, file_bytes: bytes, key: str) -> None:
        await run_in_threadpool(self._upload_sync, file_bytes, key)
        logger.debug("S3Storage: uploaded s3://%s/%s", self._bucket, key)

    async def delete(self, key: str) -> None:
        await run_in_threadpool(self._delete_sync, key)
        logger.debug("S3Storage: deleted s3://%s/%s", self._bucket, key)

    def public_url(self, key: str) -> str:
        if self._endpoint:
            # for MinIO / localstack / custom endpoint
            return f"{self._endpoint.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"


# Factory


def get_storage() -> StorageBackend:
    """
    Returns the storage backend configured via  settings.storage_backend.

    Add  STORAGE_BACKEND=s3   to your production .env to switch to S3.
    The default is  local  so no extra config is needed during development.
    """
    backend = getattr(settings, "storage_backend", "local")
    if backend == "s3":
        return S3Storage()
    return LocalStorage()


async def _cleanup_keys(storage: StorageBackend, keys: list[str]) -> None:
    """Delete storage objects without raising — used in error-recovery paths."""
    results = await asyncio.gather(
        *[storage.delete(k) for k in keys],
        return_exceptions=True,
    )
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("Cleanup failed for key %r: %s", key, result)
