"""Tests for the compliance rule engine, checker, and agent_loop integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.compliance.checker import check_compliance
from app.compliance.models import ComplianceResult
from app.models.chat import ChatStreamEvent


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

def _make_chunk(content: str | None = None,
                finish_reason: str | None = None) -> MagicMock:
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    return chunk


class TestAgentLoopCompliance:
    """Ensure the agent_loop emits a compliance event before done."""

    async def test_compliance_event_emitted_for_clean_response(self):
        from app.agent.agent_loop import run_agent

        chunks = [
            _make_chunk(content="茅台2024年营收1700亿，同比增长15%。"),
            _make_chunk(finish_reason="stop"),
        ]

        async def fake_create(**kwargs):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = fake_create
            events = [e async for e in run_agent("sess-1", "分析茅台")]

        types = [e.type for e in events]
        assert "compliance" in types
        # compliance must come before done
        assert types.index("compliance") < types.index("done")

        compliance_event = next(e for e in events if e.type == "compliance")
        assert compliance_event.compliance_passed is True
        assert compliance_event.compliance_issues == []

    async def test_compliance_event_flags_violation(self):
        from app.agent.agent_loop import run_agent

        # LLM produces non-compliant content
        chunks = [
            _make_chunk(content="保证您投资必定盈利，零风险。"),
            _make_chunk(finish_reason="stop"),
        ]

        async def fake_create(**kwargs):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = fake_create
            events = [e async for e in run_agent("sess-2", "有什么推荐")]

        compliance_event = next(e for e in events if e.type == "compliance")
        assert compliance_event.compliance_passed is False
        assert len(compliance_event.compliance_issues) > 0

        # Conversation still completes normally — text is not blocked
        types = [e.type for e in events]
        assert "done" in types
        assert "text" in types

    async def test_event_order_is_text_compliance_done(self):
        from app.agent.agent_loop import run_agent

        chunks = [
            _make_chunk(content="分析结果如下。"),
            _make_chunk(finish_reason="stop"),
        ]

        async def fake_create(**kwargs):
            async def _gen():
                for c in chunks:
                    yield c
            return _gen()

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.get_llm_client") as mock_client,
        ):
            mock_client.return_value.chat.completions.create = fake_create
            events = [e async for e in run_agent("sess-3", "你好")]

        types = [e.type for e in events]
        # Strict ordering: all text events → compliance → done
        last_text_idx = max((i for i, t in enumerate(types) if t == "text"), default=-1)
        compliance_idx = types.index("compliance")
        done_idx = types.index("done")

        assert last_text_idx < compliance_idx < done_idx
