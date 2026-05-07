import asyncio
import uuid

from qdrant_client.models import PointStruct, FilterSelector, Filter, FieldCondition, MatchValue

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.qdrant_client import get_qdrant
from app.db import document_repo
from app.doc_pipeline.parsers import get_parser
from app.doc_pipeline.chunker import chunk_blocks
from app.doc_pipeline.embedder import embed_texts

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document(self, doc_id: str, file_path: str, file_type: str) -> None:
    try:
        asyncio.run(_run_pipeline(uuid.UUID(doc_id), file_path, file_type))
    except Exception as exc:
        logger.error("pipeline_failed", doc_id=doc_id, error=str(exc), exc_info=exc)
        raise self.retry(exc=exc)


async def _run_pipeline(doc_id: uuid.UUID, file_path: str, file_type: str) -> None:
    session_factory = get_session_factory()

    async with session_factory() as session:
        async with session.begin():
            await document_repo.update_status(session, doc_id, "processing")

    try:
        parser = get_parser(file_type)
        blocks = parser.parse(file_path)
        logger.info("doc_parsed", doc_id=str(doc_id), block_count=len(blocks))

        chunks = chunk_blocks(blocks)
        logger.info("doc_chunked", doc_id=str(doc_id), chunk_count=len(chunks))

        if chunks:
            embeddings = await embed_texts([c.text for c in chunks])
            settings = get_settings()
            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_OID, f"{doc_id}:{chunk.chunk_index}")),
                    vector=embedding,
                    payload={
                        "document_id": str(doc_id),
                        "chunk_index": chunk.chunk_index,
                        "chunk_type": chunk.chunk_type,
                        "text": chunk.text,
                        "page_num": chunk.page_num,
                        "section_title": chunk.section_title,
                    },
                )
                for chunk, embedding in zip(chunks, embeddings)
            ]
            await get_qdrant().upsert(
                collection_name=settings.qdrant_collection_docs,
                points=points,
            )
            logger.info("doc_stored", doc_id=str(doc_id), point_count=len(points))

        async with session_factory() as session:
            async with session.begin():
                await document_repo.update_status(
                    session, doc_id, "ready", chunk_count=len(chunks)
                )

    except Exception as exc:
        async with session_factory() as session:
            async with session.begin():
                await document_repo.update_status(
                    session, doc_id, "failed", error_message=str(exc)
                )
        raise
