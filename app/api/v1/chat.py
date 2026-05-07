from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.agent_loop import run_agent
from app.memory.session import clear_session, load_messages
from app.models.chat import (
    ChatRequest,
    ChatStreamEvent,
    SessionHistoryResponse,
)
from app.models.common import BaseResponse

router = APIRouter(prefix="/chat", tags=["chat"])


async def _sse_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    async for event in run_agent(request.session_id, request.message):
        yield f"data: {event.model_dump_json()}\n\n"


@router.post("/completions")
async def chat_completions(request: ChatRequest):
    if request.stream:
        return StreamingResponse(
            _sse_generator(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming: collect all agent events, return final text
    content_parts: list[str] = []
    session_id = request.session_id
    async for event in run_agent(session_id, request.message):
        if event.type == "text":
            content_parts.append(event.content)

    return BaseResponse(data={"content": "".join(content_parts), "session_id": session_id})


@router.get("/sessions/{session_id}", response_model=BaseResponse[SessionHistoryResponse])
async def get_session(session_id: str):
    messages = await load_messages(session_id)
    return BaseResponse(
        data=SessionHistoryResponse(
            session_id=session_id,
            messages=messages,
            total=len(messages),
        )
    )


@router.delete("/sessions/{session_id}", response_model=BaseResponse[str])
async def delete_session(session_id: str):
    await clear_session(session_id)
    return BaseResponse(data="cleared")
