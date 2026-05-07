import redis.asyncio as aioredis
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def check_redis_connection() -> bool:
    try:
        await get_redis().ping()
        return True
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))
        return False


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
