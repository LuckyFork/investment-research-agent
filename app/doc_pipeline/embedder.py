from openai import AsyncOpenAI
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 100


async def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        logger.info("embedding_batch", start=i, count=len(batch))
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        all_embeddings.extend(item.embedding for item in response.data)

    return all_embeddings
