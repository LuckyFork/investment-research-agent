import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document


async def create_document(
    session: AsyncSession,
    doc_id: uuid.UUID,
    tenant_id: str,
    owner_user_id: str,
    filename: str,
    file_type: str,
    file_size: int,
) -> Document:
    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
    )
    session.add(doc)
    await session.flush()
    return doc


async def get_document(
    session: AsyncSession,
    doc_id: uuid.UUID,
    tenant_id: str | None = None,
    owner_user_id: str | None = None,
) -> Document | None:
    stmt = select(Document).where(Document.id == doc_id)
    if tenant_id is not None:
        stmt = stmt.where(Document.tenant_id == tenant_id)
    if owner_user_id is not None:
        stmt = stmt.where(Document.owner_user_id == owner_user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    tenant_id: str,
    owner_user_id: str,
    page: int = 1,
    size: int = 20,
) -> tuple[list[Document], int]:
    scoped = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.owner_user_id == owner_user_id,
    )
    total = (
        await session.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one()
    docs = list(
        (
            await session.execute(
                scoped
                .order_by(Document.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars()
    )
    return docs, total


async def update_status(
    session: AsyncSession,
    doc_id: uuid.UUID,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> Document | None:
    doc = await get_document(session, doc_id)
    if doc is None:
        return None
    doc.status = status
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    if error_message is not None:
        doc.error_message = error_message
    await session.flush()
    return doc


async def delete_document(session: AsyncSession, doc_id: uuid.UUID) -> bool:
    doc = await get_document(session, doc_id)
    if doc is None:
        return False
    await session.delete(doc)
    await session.flush()
    return True
