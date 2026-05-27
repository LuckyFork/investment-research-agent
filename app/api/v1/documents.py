import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.logging import get_logger
from app.core.qdrant_client import get_qdrant
from app.core.request_context import RequestContext, get_request_context
from app.db import document_repo
from app.doc_pipeline.parsers import SUPPORTED_TYPES
from app.models.common import BaseResponse
from app.models.document import (
    DocumentListItem,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.tasks.doc_tasks import process_document

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=BaseResponse[DocumentUploadResponse], status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    context: RequestContext = Depends(get_request_context),
):
    suffix = Path(file.filename or "").suffix.lstrip(".").lower()
    if suffix not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_TYPES)}",
        )

    content = await file.read()
    doc_id = uuid.uuid4()
    settings = get_settings()
    file_path = Path(settings.upload_dir) / f"{doc_id}.{suffix}"

    # Save file before committing DB record so failure is recoverable
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    try:
        async with session.begin():
            await document_repo.create_document(
                session,
                doc_id=doc_id,
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                filename=file.filename or f"upload.{suffix}",
                file_type=suffix,
                file_size=len(content),
            )
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    process_document.delay(str(doc_id), str(file_path), suffix)
    logger.info("document_uploaded", doc_id=str(doc_id), filename=file.filename)

    return BaseResponse(
        data=DocumentUploadResponse(
            document_id=doc_id,
            message="Document uploaded and queued for processing",
        )
    )


@router.get("/{doc_id}", response_model=BaseResponse[DocumentResponse])
async def get_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    context: RequestContext = Depends(get_request_context),
):
    doc = await document_repo.get_document(
        session,
        doc_id,
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return BaseResponse(data=DocumentResponse.model_validate(doc))


@router.get("", response_model=BaseResponse[DocumentListResponse])
async def list_documents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    context: RequestContext = Depends(get_request_context),
):
    docs, total = await document_repo.list_documents(
        session,
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
        page=page,
        size=size,
    )
    return BaseResponse(
        data=DocumentListResponse(
            documents=[DocumentListItem.model_validate(d) for d in docs],
            total=total,
            page=page,
            size=size,
        )
    )


@router.delete("/{doc_id}", response_model=BaseResponse[str])
async def delete_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    context: RequestContext = Depends(get_request_context),
):
    doc = await document_repo.get_document(
        session,
        doc_id,
        tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    settings = get_settings()
    await get_qdrant().delete(
        collection_name=settings.qdrant_collection_docs,
        points_selector=FilterSelector(
            filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=str(doc_id)))]
            )
        ),
    )

    async with session.begin():
        await document_repo.delete_document(session, doc_id)

    file_path = Path(settings.upload_dir) / f"{doc_id}.{doc.file_type}"
    file_path.unlink(missing_ok=True)

    return BaseResponse(data="deleted")
