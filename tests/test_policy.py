from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
from app.policy.service import evaluate_agent_decision, evaluate_tool_call


def _decision(
    *,
    intent_type: IntentType,
    action_type: ActionType,
    answer_draft: str = "回答",
    requires_tool: bool = False,
    tool_name: str = "",
    tool_args: dict | None = None,
    personalized: bool = False,
    has_sufficient_evidence: bool = True,
) -> AgentDecision:
    return AgentDecision(
        intent=IntentAssessment(
            intent_type=intent_type,
            user_goal="测试目标",
            reasoning="测试策略判断",
            confidence=0.93,
        ),
        action=ActionProposal(
            action_type=action_type,
            requires_tool=requires_tool,
            tool_name=tool_name,
            tool_args=tool_args or {},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="需要降级",
        ),
        evidence=EvidenceBundle(
            citations=[],
            has_sufficient_evidence=has_sufficient_evidence,
            evidence_gap="" if has_sufficient_evidence else "缺少证据",
        ),
        response=ResponseDraft(
            answer_draft=answer_draft,
            includes_risk_note=False,
            is_personalized=personalized,
            needs_human_review=False,
        ),
    )


class TestPolicyService:
    def test_valid_search_documents_allowed_and_sanitized(self):
        decision = evaluate_tool_call(
            "search_documents",
            {"query": "  茅台营收  ", "top_k": 99, "ignored": "x"},
            RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
        )

        assert decision.allowed is True
        assert decision.reason_code == "ALLOW_001"
        assert decision.sanitized_args == {"query": "茅台营收", "top_k": 10}

    def test_empty_query_blocked(self):
        decision = evaluate_tool_call(
            "search_documents",
            {"query": "   "},
            RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
        )

        assert decision.allowed is False
        assert decision.reason_code == "ARG_001"

    def test_unknown_tool_blocked(self):
        decision = evaluate_tool_call(
            "delete_everything",
            {},
            RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
        )

        assert decision.allowed is False
        assert decision.reason_code == "TOOL_001"

    def test_scene_policy_blocks_investment_advice(self):
        result = evaluate_agent_decision(
            _decision(
                intent_type=IntentType.PERSONALIZED_ADVICE_REQUEST,
                action_type=ActionType.ANSWER_DIRECTLY,
                personalized=True,
            ),
            RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
        )

        assert result.allowed is False
        assert result.final_action == ActionType.HANDOFF_TO_HUMAN

    def test_scene_policy_allows_read_only_search(self):
        result = evaluate_agent_decision(
            _decision(
                intent_type=IntentType.FACT_LOOKUP,
                action_type=ActionType.SEARCH_DOCUMENTS,
                requires_tool=True,
                tool_name="search_documents",
                tool_args={"query": "茅台营收"},
                has_sufficient_evidence=False,
            ),
            RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
        )

        assert result.allowed is True
        assert result.allow_tool is True


class TestAuditService:
    async def test_record_audit_event_persists_via_repo(self):
        from app.audit.service import record_audit_event

        begin_ctx = AsyncMock()
        session = MagicMock()
        session.begin = MagicMock(return_value=begin_ctx)

        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=None)
        session_factory = MagicMock(return_value=session_ctx)

        with (
            patch("app.audit.service.get_session_factory", return_value=session_factory),
            patch("app.audit.service.audit_repo.create_audit_event", new_callable=AsyncMock) as mock_create,
        ):
            await record_audit_event(
                trace_id="req-1",
                session_id="tenant-1:user-1:s1",
                tenant_id="tenant-1",
                user_id="user-1",
                channel="test",
                event_type="tool_call",
                model_version="deepseek-chat",
                prompt_version="research-agent-v2",
                rule_version="2026-05-23",
                tool_name="search_documents",
                tool_args={"query": "茅台营收"},
            )

        mock_create.assert_awaited_once()

    async def test_record_audit_event_is_best_effort(self):
        from app.audit.service import record_audit_event

        with patch(
            "app.audit.service.get_session_factory",
            side_effect=RuntimeError("db unavailable"),
        ):
            await record_audit_event(
                trace_id="req-1",
                session_id="tenant-1:user-1:s1",
                tenant_id="tenant-1",
                user_id="user-1",
                channel="test",
                event_type="error",
            )


class TestAgentLoopPolicyIntegration:
    async def test_blocked_tool_call_does_not_execute_tool(self):
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision(
                    intent_type=IntentType.FACT_LOOKUP,
                    action_type=ActionType.SEARCH_DOCUMENTS,
                    requires_tool=True,
                    tool_name="search_documents",
                    tool_args={"query": ""},
                    answer_draft="",
                    has_sufficient_evidence=False,
                ),
            ),
            patch("app.agent.agent_loop.execute_tool", new_callable=AsyncMock) as mock_execute,
        ):
            events = [
                e async for e in run_agent(
                    "sess-policy",
                    "帮我查一下",
                    RequestContext(user_id="user-1", tenant_id="tenant-1", request_id="req-1"),
                )
            ]

        mock_execute.assert_not_awaited()
        tool_done = next(e for e in events if e.type == "tool_done")
        assert "阻止" in tool_done.content
