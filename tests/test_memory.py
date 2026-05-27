"""Tests for memory compressor, session compression, and agent_loop summary injection."""

import json
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
from app.models.chat import ChatMessage, ChatStreamEvent


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw(role: str, content: str) -> bytes:
    return json.dumps({"role": role, "content": content, "created_at": 0.0}).encode()


def _make_redis(*, length: int = 0, overflow_raw: list[bytes] | None = None,
                existing_summary: bytes | None = None) -> AsyncMock:
    """Build a minimal async Redis mock."""
    mock = AsyncMock()
    mock.rpush = AsyncMock(return_value=length)
    mock.expire = AsyncMock(return_value=True)
    mock.llen = AsyncMock(return_value=length)
    mock.lrange = AsyncMock(return_value=overflow_raw or [])
    mock.get = AsyncMock(return_value=existing_summary)
    mock.set = AsyncMock(return_value=True)
    mock.ltrim = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    return mock


def _decision(answer_draft: str = "回答") -> AgentDecision:
    return AgentDecision(
        intent=IntentAssessment(
            intent_type=IntentType.RESEARCH_ANALYSIS,
            user_goal="继续分析",
            reasoning="测试摘要传递",
            confidence=0.88,
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


# ── compressor tests ──────────────────────────────────────────────────────────

class TestCompressor:
    async def test_returns_llm_response_as_summary(self):
        from app.memory.compressor import compress_old_messages

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "茅台2024年营收分析摘要"

        with patch("app.memory.compressor.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            result = await compress_old_messages(
                existing_summary="",
                raw_messages=[_raw("user", "分析茅台"), _raw("assistant", "茅台是白酒龙头")],
            )

        assert result == "茅台2024年营收分析摘要"

    async def test_includes_existing_summary_in_prompt(self):
        from app.memory.compressor import compress_old_messages

        captured: dict = {}
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "新摘要"

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("app.memory.compressor.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = fake_create
            await compress_old_messages(
                existing_summary="已有：用户在分析茅台",
                raw_messages=[_raw("user", "今年营收多少")],
            )

        user_msg_content = captured["messages"][1]["content"]
        assert "已有摘要" in user_msg_content
        assert "用户在分析茅台" in user_msg_content

    async def test_empty_input_returns_empty_string(self):
        from app.memory.compressor import compress_old_messages

        result = await compress_old_messages(existing_summary="", raw_messages=[])
        assert result == ""

    async def test_skips_malformed_raw_messages(self):
        from app.memory.compressor import compress_old_messages

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "摘要"

        with patch("app.memory.compressor.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            # Mix valid and invalid raw bytes
            result = await compress_old_messages(
                existing_summary="",
                raw_messages=[b"not-json", _raw("user", "有效消息")],
            )

        assert result == "摘要"


# ── session compression tests ─────────────────────────────────────────────────

class TestSessionCompression:
    async def test_no_compression_below_threshold(self):
        """Message count ≤ SUMMARY_THRESHOLD must not trigger compression."""
        from app.memory.session import SUMMARY_THRESHOLD, append_message

        mock_redis = _make_redis(length=SUMMARY_THRESHOLD)  # exactly at threshold

        with (
            patch("app.memory.session.get_redis", return_value=mock_redis),
            patch("app.memory.session.compress_old_messages", new_callable=AsyncMock) as mock_compress,
        ):
            await append_message("sess-1", ChatMessage(role="user", content="hello"))

        mock_compress.assert_not_awaited()

    async def test_compression_triggered_above_threshold(self):
        """Message count > SUMMARY_THRESHOLD must call compress_old_messages."""
        from app.memory.session import SUMMARY_THRESHOLD, append_message

        overflow = [_raw("user", f"msg{i}") for i in range(12)]
        mock_redis = _make_redis(length=SUMMARY_THRESHOLD + 1, overflow_raw=overflow)

        with (
            patch("app.memory.session.get_redis", return_value=mock_redis),
            patch("app.memory.session.compress_old_messages",
                  new_callable=AsyncMock, return_value="新摘要") as mock_compress,
        ):
            await append_message("sess-2", ChatMessage(role="assistant", content="回答"))

        mock_compress.assert_awaited_once()

    async def test_summary_stored_and_messages_trimmed(self):
        """After compression, summary key is SET and messages are LTRIMmed."""
        from app.memory.session import SUMMARY_THRESHOLD, append_message

        overflow = [_raw("user", "旧消息")]
        mock_redis = _make_redis(length=SUMMARY_THRESHOLD + 1, overflow_raw=overflow)

        with (
            patch("app.memory.session.get_redis", return_value=mock_redis),
            patch("app.memory.session.compress_old_messages",
                  new_callable=AsyncMock, return_value="压缩摘要"),
        ):
            await append_message("sess-3", ChatMessage(role="user", content="x"))

        mock_redis.set.assert_awaited_once()
        set_call_args = mock_redis.set.call_args
        assert "压缩摘要" in set_call_args.args or "压缩摘要" in set_call_args.kwargs.values()
        mock_redis.ltrim.assert_awaited_once()

    async def test_compression_failure_falls_back_to_ltrim(self):
        """If compression raises, session falls back to simple LTRIM (no crash)."""
        from app.memory.session import SUMMARY_THRESHOLD, append_message

        overflow = [_raw("user", "旧消息")]
        mock_redis = _make_redis(length=SUMMARY_THRESHOLD + 1, overflow_raw=overflow)

        with (
            patch("app.memory.session.get_redis", return_value=mock_redis),
            patch("app.memory.session.compress_old_messages",
                  new_callable=AsyncMock, side_effect=RuntimeError("LLM timeout")),
        ):
            # Must not raise
            await append_message("sess-4", ChatMessage(role="user", content="x"))

        # Fallback LTRIM must still be called
        mock_redis.ltrim.assert_awaited_once()

    async def test_load_summary_returns_empty_when_missing(self):
        from app.memory.session import load_summary

        mock_redis = _make_redis(existing_summary=None)
        with patch("app.memory.session.get_redis", return_value=mock_redis):
            result = await load_summary("sess-5")

        assert result == ""

    async def test_load_summary_decodes_bytes(self):
        from app.memory.session import load_summary

        mock_redis = _make_redis(existing_summary="已有摘要内容".encode())
        with patch("app.memory.session.get_redis", return_value=mock_redis):
            result = await load_summary("sess-6")

        assert result == "已有摘要内容"

    async def test_clear_session_deletes_both_keys(self):
        from app.memory.session import clear_session

        mock_redis = _make_redis()
        with patch("app.memory.session.get_redis", return_value=mock_redis):
            await clear_session("sess-7")

        mock_redis.delete.assert_awaited_once()
        # Both messages key and summary key must be deleted in one call
        delete_args = mock_redis.delete.call_args.args
        assert len(delete_args) == 2


# ── agent_loop summary injection tests ───────────────────────────────────────

class TestAgentLoopSummaryInjection:
    async def test_summary_passed_into_plan_next_step(self):
        """When load_summary returns text, agent_loop must pass it into structured planning."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages",
                  new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary",
                  new_callable=AsyncMock, return_value="用户在分析贵州茅台2024年财报"),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision(),
            ) as mock_plan,
        ):
            _ = [
                e async for e in run_agent(
                    "sess-8",
                    "继续分析",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        assert mock_plan.await_args.args[1] == "用户在分析贵州茅台2024年财报"

    async def test_empty_summary_passed_as_empty_string(self):
        """When there is no summary, planning should receive an empty string."""
        from app.agent.agent_loop import run_agent

        with (
            patch("app.agent.agent_loop.load_messages",
                  new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary",
                  new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch(
                "app.agent.agent_loop.plan_next_step",
                new_callable=AsyncMock,
                return_value=_decision(),
            ) as mock_plan,
        ):
            _ = [
                e async for e in run_agent(
                    "sess-9",
                    "你好",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        assert mock_plan.await_args.args[1] == ""
