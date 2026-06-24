import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


class CacheJSONEncoder(json.JSONEncoder):

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (UUID,)):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


async def cache_get(key: str) -> Any | None:
    try:
        raw = await redis_client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:

        logger.warning("Cache read failed for key %r", key, exc_info=True)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        raw = json.dumps(value, cls=CacheJSONEncoder)
        await redis_client.set(key, raw, ex=ttl_seconds)
    except Exception:
        logger.warning("Cache write failed for key %r", key, exc_info=True)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        await redis_client.delete(*keys)
    except Exception:
        logger.warning("Cache delete failed for keys %r", keys, exc_info=True)


async def cache_delete_pattern(pattern: str) -> None:

    try:
        keys_to_delete = []
        async for key in redis_client.scan_iter(match=pattern, count=100):
            keys_to_delete.append(key)
        if keys_to_delete:
            await redis_client.delete(*keys_to_delete)
    except Exception:
        logger.warning(
            "Cache pattern delete failed for pattern %r", pattern, exc_info=True
        )
