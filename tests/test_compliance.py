"""Tests for the compliance rule engine, checker, and agent_loop integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.compliance.checker import check_compliance
from app.compliance.models import ComplianceResult
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


# ── rule engine / checker tests ───────────────────────────────────────────────

class TestRuleEngine:
    """Verify individual rules fire on matching text and pass on clean text."""

    def test_clean_text_passes_with_no_issues(self):
        result = check_compliance("茅台2024年营收约1700亿元，同比增长15%，需注意市场波动风险。")
        assert result.passed is True
        assert result.issues == []

    def test_empty_text_passes(self):
        result = check_compliance("")
        assert result.passed is True
        assert result.issues == []

    def test_承诺收益_triggers_PRO001_error(self):
        result = check_compliance("我们保证您的投资一定盈利，请放心购买。")
        rules = [i.rule for i in result.issues]
        assert "PRO_001" in rules
        assert result.passed is False

    def test_绝对化表述_triggers_PRO002_error(self):
        result = check_compliance("该股票必涨，稳赚不赔，零风险投资机会。")
        rules = [i.rule for i in result.issues]
        assert "PRO_002" in rules
        assert result.passed is False

    def test_内幕信息_triggers_PRO003_error(self):
        result = check_compliance("根据内部消息，该公司下季度将并购，建议提前布局。")
        rules = [i.rule for i in result.issues]
        assert "PRO_003" in rules
        assert result.passed is False

    def test_否认亏损_triggers_PRO004_error(self):
        result = check_compliance("购买此基金亏损绝对不会发生，历史业绩稳健。")
        rules = [i.rule for i in result.issues]
        assert "PRO_004" in rules
        assert result.passed is False

    def test_强烈推荐_triggers_PRW002_warning(self):
        result = check_compliance("强烈推荐买入，当前估值具备吸引力。")
        rules = [i.rule for i in result.issues]
        assert "PRW_002" in rules
        # warning only → passed should still be True
        assert result.passed is True

    def test_目标价_triggers_PRW003_warning(self):
        result = check_compliance("我们给出目标价45.5元，上行空间约30%。")
        rules = [i.rule for i in result.issues]
        assert "PRW_003" in rules
        assert result.passed is True  # warning, not error

    def test_multiple_violations_all_collected(self):
        text = "必涨，零风险，保证盈利，根据内幕消息。"
        result = check_compliance(text)
        assert len(result.issues) >= 3
        assert result.passed is False

    def test_snippet_contains_matched_text(self):
        result = check_compliance("该股票必涨，值得关注。")
        assert any("必涨" in i.snippet for i in result.issues)


class TestComplianceResult:
    """Verify passed flag logic."""

    def test_passed_false_when_error_exists(self):
        result = check_compliance("保证盈利，100%涨。")
        assert result.passed is False

    def test_passed_true_with_only_warnings(self):
        result = check_compliance("强烈推荐买入，目标价50元。")
        levels = {i.level for i in result.issues}
        if levels:
            assert "error" not in levels
        assert result.passed is True

    def test_issues_are_complianceissue_instances(self):
        from app.compliance.models import ComplianceIssue
        result = check_compliance("必涨。")
        for issue in result.issues:
            assert isinstance(issue, ComplianceIssue)
            assert issue.level in ("warning", "error")
            assert issue.rule
            assert issue.description


# ── agent_loop integration tests ──────────────────────────────────────────────

def _decision(answer_draft: str) -> AgentDecision:
    return AgentDecision(
        intent=IntentAssessment(
            intent_type=IntentType.RESEARCH_ANALYSIS,
            user_goal="分析内容",
            reasoning="测试合规流程",
            confidence=0.91,
        ),
        action=ActionProposal(
            action_type=ActionType.ANSWER_DIRECTLY,
            requires_tool=False,
            tool_name="",
            tool_args={},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="",
        ),
        evidence=EvidenceBundle(
            citations=[],
            has_sufficient_evidence=True,
            evidence_gap="",
        ),
        response=ResponseDraft(
            answer_draft=answer_draft,
            includes_risk_note=False,
            is_personalized=False,
            needs_human_review=False,
        ),
    )


class TestAgentLoopCompliance:
    """Ensure the agent_loop emits a compliance event before done."""

    async def test_compliance_event_emitted_for_clean_response(self):
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision("茅台2024年营收1700亿，同比增长15%。"),
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-1",
                    "分析茅台",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        types = [e.type for e in events]
        assert "compliance" in types
        # compliance must come before done
        assert types.index("compliance") < types.index("done")

        compliance_event = next(e for e in events if e.type == "compliance")
        assert compliance_event.compliance_passed is True
        assert compliance_event.compliance_issues == []

    async def test_compliance_event_flags_violation(self):
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision("保证您投资必定盈利，零风险。"),
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-2",
                    "有什么推荐",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        compliance_event = next(e for e in events if e.type == "compliance")
        assert compliance_event.compliance_passed is False
        assert len(compliance_event.compliance_issues) > 0

        # Conversation still completes normally, but raw text is blocked and replaced
        types = [e.type for e in events]
        assert "done" in types
        assert "text" in types
        blocked_text = "".join(e.content for e in events if e.type == "text")
        assert "合规保护" in blocked_text
        assert "保证您投资必定盈利" not in blocked_text

    async def test_event_order_is_compliance_text_done(self):
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision("分析结果如下。"),
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-3",
                    "你好",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        types = [e.type for e in events]
        # Strict ordering: compliance gate must run before any user-visible text
        first_text_idx = min((i for i, t in enumerate(types) if t == "text"), default=-1)
        compliance_idx = types.index("compliance")
        done_idx = types.index("done")

        assert compliance_idx < first_text_idx < done_idx
