"""Tests for RAG retriever, tool executor, and the structured agent loop."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.request_context import RequestContext
from app.models.decision import (
    ActionProposal,
    ActionType,
    AgentDecision,
    EvidenceBundle,
    IntentAssessment,
    IntentType,
    ResponseDraft,
)


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


def _decision(
    *,
    intent_type: IntentType,
    action_type: ActionType,
    answer_draft: str,
    requires_tool: bool = False,
    tool_name: str = "",
    tool_args: dict | None = None,
    has_sufficient_evidence: bool = True,
) -> AgentDecision:
    return AgentDecision(
        intent=IntentAssessment(
            intent_type=intent_type,
            user_goal="分析问题",
            reasoning="测试用结构化决策",
            confidence=0.92,
        ),
        action=ActionProposal(
            action_type=action_type,
            requires_tool=requires_tool,
            tool_name=tool_name,
            tool_args=tool_args or {},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="",
        ),
        evidence=EvidenceBundle(
            citations=[],
            has_sufficient_evidence=has_sufficient_evidence,
            evidence_gap="" if has_sufficient_evidence else "缺少文档依据",
        ),
        response=ResponseDraft(
            answer_draft=answer_draft,
            includes_risk_note=False,
            is_personalized=False,
            needs_human_review=False,
        ),
    )


# ── retriever tests ───────────────────────────────────────────────────────────

class TestRetriever:
    async def test_search_embeds_and_queries_qdrant(self):
        from app.agent.retriever import search_documents

        fake_hits = [_qdrant_hit("茅台2024年营收1700亿")]
        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=MagicMock(points=fake_hits))

        with (
            patch("app.agent.retriever.embed_texts", new_callable=AsyncMock,
                  return_value=[[0.1] * 1536]),
            patch("app.agent.retriever.get_qdrant", return_value=mock_qdrant),
        ):
            results = await search_documents(
                "茅台营收",
                RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )

        assert len(results) == 1
        assert results[0]["text"] == "茅台2024年营收1700亿"
        assert results[0]["score"] == 0.85
        mock_qdrant.query_points.assert_awaited_once()

    async def test_search_returns_empty_when_no_hits(self):
        from app.agent.retriever import search_documents

        mock_qdrant = AsyncMock()
        mock_qdrant.query_points = AsyncMock(return_value=MagicMock(points=[]))

        with (
            patch("app.agent.retriever.embed_texts", new_callable=AsyncMock,
                  return_value=[[0.0] * 1536]),
            patch("app.agent.retriever.get_qdrant", return_value=mock_qdrant),
        ):
            results = await search_documents(
                "不存在的内容",
                RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )

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
            result = await execute_tool(
                "search_documents",
                {"query": "营收"},
                RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )

        assert "营收数据" in result
        assert "doc-1" in result
        assert "财务摘要" in result

    async def test_no_results_returns_not_found_message(self):
        from app.agent.tools import execute_tool

        with patch("app.agent.tools._search_docs", new_callable=AsyncMock, return_value=[]):
            result = await execute_tool(
                "search_documents",
                {"query": "xxx"},
                RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )

        assert "未" in result

    async def test_unknown_tool_raises(self):
        from app.agent.tools import execute_tool

        with pytest.raises(ValueError, match="Unknown tool"):
            await execute_tool(
                "nonexistent_tool",
                {},
                RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )


# ── agent loop tests ──────────────────────────────────────────────────────────

class TestAgentLoop:
    async def test_direct_answer_no_tool(self):
        """Structured decision can return a direct answer without tools."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision(
                    intent_type=IntentType.FACT_LOOKUP,
                    action_type=ActionType.ANSWER_DIRECTLY,
                    answer_draft="这是回答",
                ),
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-1",
                    "你好",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        types = [e.type for e in events]
        assert "error" not in types
        assert types[-1] == "done"
        text = "".join(e.content for e in events if e.type == "text")
        assert text == "这是回答"

    async def test_tool_call_then_final_answer(self):
        """Structured decision requests a tool, then final answer is generated from tool output."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision(
                    intent_type=IntentType.FACT_LOOKUP,
                    action_type=ActionType.SEARCH_DOCUMENTS,
                    answer_draft="",
                    requires_tool=True,
                    tool_name="search_documents",
                    tool_args={"query": "茅台营收"},
                    has_sufficient_evidence=False,
                ),
            ),
            patch("app.agent.agent_loop.execute_tool", new_callable=AsyncMock,
                  return_value="茅台2024年营收1700亿元"),
            patch(
                "app.agent.agent_loop.generate_answer_from_tool",
                new_callable=AsyncMock,
                return_value="根据文档：营收1700亿",
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-2",
                    "茅台营收多少",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        types = [e.type for e in events]
        assert "tool_start" in types
        assert "tool_done" in types
        assert "text" in types
        assert types[-1] == "done"
        assert "error" not in types

        tool_start = next(e for e in events if e.type == "tool_start")
        assert tool_start.tool_name == "search_documents"

    async def test_error_event_on_exception(self):
        """If decision planning raises, agent yields error event rather than propagating."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.plan_next_step", new_callable=AsyncMock),
        ):
            from app.agent.agent_loop import plan_next_step as mock_plan
            mock_plan.side_effect = RuntimeError("LLM timeout")
            events = [
                e async for e in run_agent(
                    "sess-3",
                    "出错了",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        assert any(e.type == "error" for e in events)
        error_event = next(e for e in events if e.type == "error")
        assert "LLM timeout" in error_event.content
