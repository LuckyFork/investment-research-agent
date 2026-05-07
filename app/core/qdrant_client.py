from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-3-small

_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


async def ensure_collections() -> None:
    settings = get_settings()
    client = get_qdrant()

    for collection_name in (settings.qdrant_collection_docs, settings.qdrant_collection_memory):
        exists = await client.collection_exists(collection_name)
        if not exists:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created", collection=collection_name)


async def check_qdrant_connection() -> bool:
    try:
        await get_qdrant().get_collections()
        return True
    except Exception as e:
        logger.error("qdrant_connection_failed", error=str(e))
        return False


async def close_qdrant() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None
