import json
from app.core.redis_client import get_redis
from app.core.logging import get_logger
from app.memory.compressor import compress_old_messages
from app.models.chat import ChatMessage

logger = get_logger(__name__)

SESSION_TTL = 86400       # 24 hours
SUMMARY_THRESHOLD = 30   # trigger compression when message count exceeds this
KEEP_RECENT = 20          # messages to retain after compression
MAX_TURNS = 20            # fallback hard-cap (used if compression fails)

_KEY_PREFIX = "chat:session:"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}:messages"


def _summary_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}{session_id}:summary"


async def load_messages(session_id: str) -> list[ChatMessage]:
    raw = await get_redis().lrange(_key(session_id), 0, -1)
    messages = [ChatMessage(**json.loads(r)) for r in raw]
    logger.debug("session_loaded", session_id=session_id, count=len(messages))
    return messages


async def load_summary(session_id: str) -> str:
    """Return the compressed history summary, or '' if none exists."""
    raw = await get_redis().get(_summary_key(session_id))
    if raw is None:
        return ""
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def append_message(session_id: str, message: ChatMessage) -> None:
    redis = get_redis()
    key = _key(session_id)
    sum_key = _summary_key(session_id)

    await redis.rpush(key, message.model_dump_json())
    await redis.expire(key, SESSION_TTL)

    length = await redis.llen(key)

    if length > SUMMARY_THRESHOLD:
        overflow_count = length - KEEP_RECENT
        overflow_raw = await redis.lrange(key, 0, overflow_count - 1)

        existing_raw = await redis.get(sum_key)
        existing_summary = (
            existing_raw.decode() if isinstance(existing_raw, bytes) else (existing_raw or "")
        )

        try:
            new_summary = await compress_old_messages(existing_summary, overflow_raw)
            await redis.set(sum_key, new_summary, ex=SESSION_TTL)
            await redis.ltrim(key, overflow_count, -1)
            logger.info("session_compressed", session_id=session_id,
                        compressed=overflow_count, kept=KEEP_RECENT)
        except Exception as exc:
            # Compression failed — fall back to simple truncation so the session
            # stays bounded even without LLM availability.
            logger.error("session_compression_failed", session_id=session_id, error=str(exc))
            await redis.ltrim(key, length - MAX_TURNS * 2, -1)


async def clear_session(session_id: str) -> None:
    await get_redis().delete(_key(session_id), _summary_key(session_id))
    logger.info("session_cleared", session_id=session_id)
