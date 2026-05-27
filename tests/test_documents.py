import uuid
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch, call
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.core.db import get_db_session
from app.db.models import Document


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_doc(**kwargs) -> Document:
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id="tenant-1",
        owner_user_id="user-1",
        filename="report.pdf",
        file_type="pdf",
        file_size=1024,
        status="pending",
        chunk_count=0,
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    doc = MagicMock(spec=Document)
    for k, v in defaults.items():
        setattr(doc, k, v)
    return doc


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = cm
    return session


@pytest.fixture
async def doc_client(mock_session):
    _app = create_app()

    async def _override_db():
        yield mock_session

    _app.dependency_overrides[get_db_session] = _override_db

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as ac:
        yield ac


# ── upload tests ──────────────────────────────────────────────────────────────

class TestUploadDocument:
    async def test_upload_pdf_success(self, doc_client, mock_session, auth_headers):
        doc = _make_doc()

        mock_file = AsyncMock()
        mock_file.__aenter__ = AsyncMock(return_value=mock_file)
        mock_file.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.api.v1.documents.document_repo.create_document", new_callable=AsyncMock, return_value=doc),
            patch("aiofiles.open", return_value=mock_file),
            patch("app.api.v1.documents.process_document") as mock_task,
        ):
            mock_task.delay = MagicMock()
            resp = await doc_client.post(
                "/api/v1/documents/upload",
                files={"file": ("report.pdf", b"%PDF-fake", "application/pdf")},
                headers=auth_headers,
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["success"] is True
        assert "document_id" in body["data"]
        mock_task.delay.assert_called_once()

    async def test_upload_unsupported_type_rejected(self, doc_client, auth_headers):
        resp = await doc_client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.docx", b"fake", "application/octet-stream")},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_upload_txt_success(self, doc_client, mock_session, auth_headers):
        doc = _make_doc(filename="notes.txt", file_type="txt")

        mock_file = AsyncMock()
        mock_file.__aenter__ = AsyncMock(return_value=mock_file)
        mock_file.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.api.v1.documents.document_repo.create_document", new_callable=AsyncMock, return_value=doc),
            patch("aiofiles.open", return_value=mock_file),
            patch("app.api.v1.documents.process_document") as mock_task,
        ):
            mock_task.delay = MagicMock()
            resp = await doc_client.post(
                "/api/v1/documents/upload",
                files={"file": ("notes.txt", b"hello world", "text/plain")},
                headers=auth_headers,
            )

        assert resp.status_code == 202


# ── get / list tests ──────────────────────────────────────────────────────────

class TestGetDocument:
    async def test_get_existing_document(self, doc_client, auth_headers):
        doc = _make_doc(status="ready", chunk_count=12)

        with patch("app.api.v1.documents.document_repo.get_document", new_callable=AsyncMock, return_value=doc):
            resp = await doc_client.get(f"/api/v1/documents/{doc.id}", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "ready"
        assert body["data"]["chunk_count"] == 12

    async def test_get_nonexistent_returns_404(self, doc_client, auth_headers):
        with patch("app.api.v1.documents.document_repo.get_document", new_callable=AsyncMock, return_value=None):
            resp = await doc_client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers)

        assert resp.status_code == 404

    async def test_list_returns_paginated(self, doc_client, auth_headers):
        docs = [_make_doc(status="ready") for _ in range(3)]

        with patch(
            "app.api.v1.documents.document_repo.list_documents",
            new_callable=AsyncMock,
            return_value=(docs, 3),
        ):
            resp = await doc_client.get("/api/v1/documents?page=1&size=20", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["documents"]) == 3


# ── delete tests ──────────────────────────────────────────────────────────────

class TestDeleteDocument:
    async def test_delete_existing(self, doc_client, auth_headers):
        doc = _make_doc(status="ready")
        mock_qdrant = AsyncMock()

        with (
            patch("app.api.v1.documents.document_repo.get_document", new_callable=AsyncMock, return_value=doc),
            patch("app.api.v1.documents.document_repo.delete_document", new_callable=AsyncMock),
            patch("app.api.v1.documents.get_qdrant", return_value=mock_qdrant),
        ):
            resp = await doc_client.delete(f"/api/v1/documents/{doc.id}", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["data"] == "deleted"
        mock_qdrant.delete.assert_awaited_once()

    async def test_delete_nonexistent_returns_404(self, doc_client, auth_headers):
        with patch("app.api.v1.documents.document_repo.get_document", new_callable=AsyncMock, return_value=None):
            resp = await doc_client.delete(f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers)

        assert resp.status_code == 404


# ── pipeline task tests ───────────────────────────────────────────────────────

class TestDocumentPipeline:
    async def test_pipeline_parses_chunks_embeds_stores(self):
        from app.doc_pipeline.parsers.base import ParsedBlock
        from app.doc_pipeline.chunker import TextChunk
        from app.tasks.doc_tasks import _run_pipeline

        doc_id = uuid.uuid4()
        blocks = [ParsedBlock(type="paragraph", text="茅台2024年营收1700亿")]
        chunks = [TextChunk(text="茅台2024年营收1700亿", chunk_index=0, chunk_type="paragraph", page_num=1, section_title="")]
        embeddings = [[0.1] * 1536]

        mock_qdrant = AsyncMock()

        # session.begin() must return an async context manager (not a coroutine)
        begin_ctx = AsyncMock()
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=begin_ctx)

        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_factory = MagicMock(return_value=session_ctx)

        with (
            patch("app.tasks.doc_tasks.get_session_factory", return_value=mock_factory),
            patch("app.tasks.doc_tasks.document_repo.update_status", new_callable=AsyncMock),
            patch("app.tasks.doc_tasks.document_repo.get_document", new_callable=AsyncMock,
                  return_value=_make_doc()),
            patch("app.tasks.doc_tasks.get_parser") as mock_get_parser,
            patch("app.tasks.doc_tasks.chunk_blocks", return_value=chunks),
            patch("app.tasks.doc_tasks.embed_texts", new_callable=AsyncMock, return_value=embeddings),
            patch("app.tasks.doc_tasks.get_qdrant", return_value=mock_qdrant),
        ):
            mock_parser = MagicMock()
            mock_parser.parse.return_value = blocks
            mock_get_parser.return_value = mock_parser

            await _run_pipeline(doc_id, "/fake/path.pdf", "pdf")

        mock_parser.parse.assert_called_once_with("/fake/path.pdf")
        mock_qdrant.upsert.assert_awaited_once()

    async def test_pipeline_marks_failed_on_parse_error(self):
        from app.tasks.doc_tasks import _run_pipeline

        doc_id = uuid.uuid4()
        begin_ctx = AsyncMock()
        mock_session = MagicMock()
        mock_session.begin = MagicMock(return_value=begin_ctx)

        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_factory = MagicMock(return_value=session_ctx)

        with (
            patch("app.tasks.doc_tasks.get_session_factory", return_value=mock_factory),
            patch("app.tasks.doc_tasks.document_repo.update_status", new_callable=AsyncMock) as mock_update,
            patch("app.tasks.doc_tasks.document_repo.get_document", new_callable=AsyncMock,
                  return_value=_make_doc()),
            patch("app.tasks.doc_tasks.get_parser") as mock_get_parser,
        ):
            mock_parser = MagicMock()
            mock_parser.parse.side_effect = RuntimeError("corrupt file")
            mock_get_parser.return_value = mock_parser

            with pytest.raises(RuntimeError, match="corrupt file"):
                await _run_pipeline(doc_id, "/fake/bad.pdf", "pdf")

            # update_status should have been called with "failed"
            statuses = [c.args[2] for c in mock_update.call_args_list]
            assert "failed" in statuses
