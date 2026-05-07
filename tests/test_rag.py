"""Tests for RAG retriever, tool executor, and the agentic loop."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.chat import ChatStreamEvent


# ── helpers ───────────────────────────────────────────────────────────────────

def _qdrant_hit(text: str, score: float = 0.85, doc_id: str = "doc-1") -> MagicMock:
    hit = MagicMock()
    hit.score = score
    hit.payload = {
        "text": text,
        "document_id": doc_id,
        "chunk_index": 0,
        "page_num": 1,
        "section_title": "财务分析",
    }
    return hit


def _make_chunk(
    content: str | None = None,
    finish_reason: str | None = None,
    tool_calls=None,
) -> MagicMock:
    """Build a minimal OpenAI streaming chunk mock."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    return chunk


# ── retriever tests ───────────────────────────────────────────────────────────

class TestRetriever:
    async def test_search_embeds_and_queries_qdrant(self):
        from app.agent.retriever import search_documents

        fake_hits = [_qdrant_hit("茅台2024年营收1700亿")]
        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=fake_hits)

        with (
            patch("app.agent.retriever.embed_texts", new_callable=AsyncMock,
                  return_value=[[0.1] * 1536]),
            patch("app.agent.retriever.get_qdrant", return_value=mock_qdrant),
        ):
            results = await search_documents("茅台营收")

        assert len(results) == 1
        assert results[0]["text"] == "茅台2024年营收1700亿"
        assert results[0]["score"] == 0.85
        mock_qdrant.search.assert_awaited_once()

    async def test_search_returns_empty_when_no_hits(self):
        from app.agent.retriever import search_documents

        mock_qdrant = AsyncMock()
        mock_qdrant.search = AsyncMock(return_value=[])

        with (
            patch("app.agent.retriever.embed_texts", new_callable=AsyncMock,
                  return_value=[[0.0] * 1536]),
            patch("app.agent.retriever.get_qdrant", return_value=mock_qdrant),
        ):
            results = await search_documents("不存在的内容")

        assert results == []


# ── tools executor tests ──────────────────────────────────────────────────────

class TestToolsExecutor:
    async def test_search_documents_formats_results(self):
        from app.agent.tools import execute_tool

        fake_results = [
            {
                "text": "营收数据",
                "document_id": "doc-1",
                "score": 0.9,
                "chunk_index": 0,
                "page_num": 3,
                "section_title": "财务摘要",
            }
        ]
        with patch("app.agent.tools._search_docs", new_callable=AsyncMock,
                   return_value=fake_results):
            result = await execute_tool("search_documents", {"query": "营收"})

        assert "营收数据" in result
        assert "doc-1" in result
        assert "财务摘要" in result

    async def test_no_results_returns_not_found_message(self):
        from app.agent.tools import execute_tool

        with patch("app.agent.tools._search_docs", new_callable=AsyncMock, return_value=[]):
            result = await execute_tool("search_documents", {"query": "xxx"})

        assert "未" in result

    async def test_unknown_tool_raises(self):
        from app.agent.tools import execute_tool

        with pytest.raises(ValueError, match="Unknown tool"):
            await execute_tool("nonexistent_tool", {})


# ── agent loop tests ──────────────────────────────────────────────────────────

class TestAgentLoop:
    async def test_direct_answer_no_tool(self):
        """When LLM returns stop without tool_calls, events are text* + done."""
        from app.agent.agent_loop import run_agent

        chunks = [
            _make_chunk(content="这是"),
            _make_chunk(content="回答"),
            _make_chunk(content=None, finish_reason="stop"),
        ]

        async def fake_stream(**kwargs):
            for c in chunks:
                yield c

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=fake_stream()
            )
            events = [e async for e in run_agent("sess-1", "你好")]

        types = [e.type for e in events]
        assert "error" not in types
        assert types[-1] == "done"
        text = "".join(e.content for e in events if e.type == "text")
        assert text == "这是回答"

    async def test_tool_call_then_final_answer(self):
        """LLM calls search_documents, then produces final text answer."""
        from app.agent.agent_loop import run_agent

        # Round 1: model requests a tool call
        tc_delta_1 = MagicMock()
        tc_delta_1.index = 0
        tc_delta_1.id = "call-abc"
        tc_delta_1.function = MagicMock()
        tc_delta_1.function.name = "search_documents"
        tc_delta_1.function.arguments = '{"query": "茅台营收"}'

        round1_chunks = [
            _make_chunk(content=None, tool_calls=[tc_delta_1]),
            _make_chunk(content=None, finish_reason="tool_calls"),
        ]

        # Round 2: model produces final answer
        round2_chunks = [
            _make_chunk(content="根据文档：营收1700亿"),
            _make_chunk(content=None, finish_reason="stop"),
        ]

        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            source = round1_chunks if call_count == 1 else round2_chunks

            async def _gen():
                for c in source:
                    yield c

            return _gen()

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
            patch("app.agent.agent_loop.execute_tool", new_callable=AsyncMock,
                  return_value="茅台2024年营收1700亿元"),
        ):
            mock_client.return_value.chat.completions.create = fake_create
            events = [e async for e in run_agent("sess-2", "茅台营收多少")]

        types = [e.type for e in events]
        assert "tool_start" in types
        assert "tool_done" in types
        assert "text" in types
        assert types[-1] == "done"
        assert "error" not in types

        tool_start = next(e for e in events if e.type == "tool_start")
        assert tool_start.tool_name == "search_documents"

    async def test_error_event_on_exception(self):
        """If LLM call raises, agent yields error event rather than propagating."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = AsyncMock(
                side_effect=RuntimeError("LLM timeout")
            )
            events = [e async for e in run_agent("sess-3", "出错了")]

        assert any(e.type == "error" for e in events)
        error_event = next(e for e in events if e.type == "error")
        assert "LLM timeout" in error_event.content
