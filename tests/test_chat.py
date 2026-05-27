import json
import pytest
from unittest.mock import AsyncMock, patch

from app.models.chat import ChatStreamEvent


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


async def _fake_agent_stream(*args, **kwargs):
    """Fake run_agent that yields text + done events."""
    yield ChatStreamEvent(type="text", content="这是")
    yield ChatStreamEvent(type="text", content="一个")
    yield ChatStreamEvent(type="text", content="测试回答")
    yield ChatStreamEvent(type="done", session_id=args[0] if args else "s1")


async def _fake_agent_with_tool(*args, **kwargs):
    """Fake run_agent that yields tool_start → tool_done → text → done."""
    yield ChatStreamEvent(type="tool_start", tool_name="search_documents", content="茅台营收")
    yield ChatStreamEvent(type="tool_done", tool_name="search_documents", content="营收1700亿")
    yield ChatStreamEvent(type="text", content="根据文档，茅台2024年营收1700亿")
    yield ChatStreamEvent(type="done", session_id=args[0] if args else "s1")


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis_session():
    store: list[str] = []

    async def fake_load(session_id):
        from app.models.chat import ChatMessage
        return [ChatMessage(**json.loads(m)) for m in store]

    async def fake_append(session_id, message):
        store.append(message.model_dump_json())

    async def fake_clear(session_id):
        store.clear()

    with (
        # Patch at every import site that binds these names
        patch("app.agent.agent_loop.load_messages", side_effect=fake_load),
        patch("app.agent.agent_loop.append_message", side_effect=fake_append),
        patch("app.api.v1.chat.load_messages", side_effect=fake_load),
        patch("app.api.v1.chat.clear_session", side_effect=fake_clear),
    ):
        yield store


# ── non-streaming tests ───────────────────────────────────────────────────────

class TestChatNonStream:
    async def test_returns_content(self, client, mock_redis_session, auth_headers):
        with patch("app.api.v1.chat.run_agent", side_effect=_fake_agent_stream):
            resp = await client.post(
                "/api/v1/chat/completions",
                json={"session_id": "s1", "message": "你好", "stream": False},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["content"] == "这是一个测试回答"
        assert body["data"]["session_id"] == "s1"

    async def test_empty_message_rejected(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/chat/completions",
            json={"session_id": "s1", "message": "", "stream": False},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_blank_message_rejected(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/chat/completions",
            json={"session_id": "s1", "message": "   ", "stream": False},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_missing_headers_rejected(self, client):
        resp = await client.post(
            "/api/v1/chat/completions",
            json={"session_id": "s1", "message": "你好", "stream": False},
        )
        assert resp.status_code == 401


# ── streaming tests ───────────────────────────────────────────────────────────

class TestChatStream:
    async def test_stream_event_sequence(self, client, auth_headers):
        with patch("app.api.v1.chat.run_agent", side_effect=_fake_agent_stream):
            resp = await client.post(
                "/api/v1/chat/completions",
                json={"session_id": "s2", "message": "分析茅台", "stream": True},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse(resp.text)
        text_events = [e for e in events if e["type"] == "text"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(text_events) == 3
        assert "".join(e["content"] for e in text_events) == "这是一个测试回答"
        assert len(done_events) == 1
        assert done_events[0]["session_id"] == "s2"

    async def test_stream_includes_tool_events(self, client, auth_headers):
        with patch("app.api.v1.chat.run_agent", side_effect=_fake_agent_with_tool):
            resp = await client.post(
                "/api/v1/chat/completions",
                json={"session_id": "s3", "message": "茅台2024营收是多少", "stream": True},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_done" in types
        assert "text" in types
        assert types[-1] == "done"

        tool_start = next(e for e in events if e["type"] == "tool_start")
        assert tool_start["tool_name"] == "search_documents"


# ── session endpoint tests ────────────────────────────────────────────────────

class TestSessionEndpoints:
    async def test_get_session_history(self, client, mock_redis_session, auth_headers):
        from app.models.chat import ChatMessage
        msg = ChatMessage(role="user", content="历史消息")
        mock_redis_session.append(msg.model_dump_json())

        resp = await client.get("/api/v1/chat/sessions/s4", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 1
        assert body["data"]["messages"][0]["content"] == "历史消息"

    async def test_delete_clears_session(self, client, mock_redis_session, auth_headers):
        from app.models.chat import ChatMessage
        mock_redis_session.append(ChatMessage(role="user", content="x").model_dump_json())

        resp = await client.delete("/api/v1/chat/sessions/s5", headers=auth_headers)
        assert resp.status_code == 200
        assert mock_redis_session == []
