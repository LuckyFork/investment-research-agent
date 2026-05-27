from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.request_context import RequestContext
from app.doc_pipeline.embedder import embed_texts
from app.core.qdrant_client import get_qdrant
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SCORE_THRESHOLD = 0.4


async def search_documents(
    query: str,
    context: RequestContext,
    top_k: int = 5,
) -> list[dict]:
    """Embed query and retrieve the most relevant document chunks from Qdrant."""
    settings = get_settings()

    query_vec = (await embed_texts([query]))[0]
    logger.info("qdrant_search", query=query[:80], top_k=top_k)

    response = await get_qdrant().query_points(
        collection_name=settings.qdrant_collection_docs,
        query=query_vec,
        limit=top_k,
        score_threshold=SCORE_THRESHOLD,
        query_filter=Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=context.tenant_id)),
                FieldCondition(key="owner_user_id", match=MatchValue(value=context.user_id)),
            ]
        ),
        with_payload=True,
    )

    results = [
        {
            "text": hit.payload.get("text", ""),
            "document_id": hit.payload.get("document_id", ""),
            "score": round(hit.score, 4),
            "chunk_index": hit.payload.get("chunk_index", 0),
            "page_num": hit.payload.get("page_num", 0),
            "section_title": hit.payload.get("section_title", ""),
        }
        for hit in response.points
    ]

    logger.info("qdrant_search_done", hits=len(results))
    return results
