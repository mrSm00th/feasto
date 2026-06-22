import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client: redis.Redis = redis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
)


async def ping_redis() -> bool:

    try:
        return await redis_client.ping()
    except Exception:
        logger.warning("Redis ping failed — caching will be unavailable", exc_info=True)
        return False
