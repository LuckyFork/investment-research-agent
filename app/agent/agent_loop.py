"""Streaming agentic loop: user message → optional tool calls → final streamed answer."""

import json
from typing import AsyncGenerator

from app.agent.llm_client import SYSTEM_PROMPT, get_llm_client
from app.agent.tools import TOOLS, execute_tool
from app.compliance.checker import check_compliance
from app.core.config import get_settings
from app.core.logging import get_logger
from app.memory.session import append_message, load_messages, load_summary
from app.models.chat import ChatMessage, ChatStreamEvent

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 3  # prevent runaway loops


def _build_oai_messages(history: list[ChatMessage], summary: str = "") -> list[dict]:
    system = SYSTEM_PROMPT
    if summary:
        system = f"{SYSTEM_PROMPT}\n\n[历史对话背景]\n{summary}"
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m.role, "content": m.content} for m in history]
    return msgs


async def run_agent(
    session_id: str,
    user_message: str,
) -> AsyncGenerator[ChatStreamEvent, None]:
    """
    Full agentic cycle — yields ChatStreamEvent objects:
      tool_start  → model decided to call a tool
      tool_done   → tool returned its result
      text        → streaming token from the final LLM response
      done        → conversation turn complete
      error       → unhandled exception during the loop
    """
    settings = get_settings()

    # ── 1. Load history, summary, and append user message ────────────────────
    history, summary = await load_messages(session_id), await load_summary(session_id)
    user_msg = ChatMessage(role="user", content=user_message)
    await append_message(session_id, user_msg)
    history.append(user_msg)

    oai_messages = _build_oai_messages(history, summary)

    try:
        # ── 2. Agentic tool-use loop ──────────────────────────────────────────
        for _round in range(MAX_TOOL_ROUNDS):
            # Stream the current round; detect tool_calls vs stop inline.
            stream = await get_llm_client().chat.completions.create(
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                messages=oai_messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
            )

            finish_reason: str | None = None
            # Accumulate per-index tool call data  {index: {id, name, args}}
            tc_acc: dict[int, dict] = {}
            content_parts: list[str] = []

            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta

                # Forward text content to caller immediately
                if delta.content:
                    content_parts.append(delta.content)
                    yield ChatStreamEvent(type="text", content=delta.content)

                # Accumulate tool_call deltas (args arrive in fragments)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tc_acc:
                            tc_acc[idx] = {
                                "id": tc_delta.id or "",
                                "name": tc_delta.function.name if tc_delta.function else "",
                                "args": "",
                            }
                        if tc_delta.id:
                            tc_acc[idx]["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            tc_acc[idx]["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            tc_acc[idx]["args"] += tc_delta.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            # ── 2a. Model finished with text → compliance check → done ────────
            if finish_reason == "stop":
                full_reply = "".join(content_parts)

                # Run synchronous rule-based compliance check
                cr = check_compliance(full_reply)
                yield ChatStreamEvent(
                    type="compliance",
                    compliance_passed=cr.passed,
                    compliance_issues=[i.model_dump() for i in cr.issues],
                )

                assistant_msg = ChatMessage(role="assistant", content=full_reply)
                await append_message(session_id, assistant_msg)
                yield ChatStreamEvent(type="done", session_id=session_id)
                return

            # ── 2b. Model wants to call tools ─────────────────────────────────
            if finish_reason == "tool_calls" and tc_acc:
                # Build the assistant message that carries the tool_calls list
                tool_calls_payload = [
                    {
                        "id": tc_acc[i]["id"],
                        "type": "function",
                        "function": {
                            "name": tc_acc[i]["name"],
                            "arguments": tc_acc[i]["args"],
                        },
                    }
                    for i in sorted(tc_acc)
                ]
                oai_messages.append(
                    {"role": "assistant", "tool_calls": tool_calls_payload}
                )

                # Execute each tool and append its result message
                for tc in tool_calls_payload:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    yield ChatStreamEvent(
                        type="tool_start",
                        tool_name=name,
                        content=args.get("query", name),
                    )

                    result = await execute_tool(name, args)

                    yield ChatStreamEvent(
                        type="tool_done",
                        tool_name=name,
                        content=result[:600],  # preview for frontend
                    )

                    oai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        }
                    )

                # Continue loop: next iteration will produce the final answer
                continue

            # Unexpected finish reason — break out of loop
            logger.warning("agent_unexpected_finish", reason=finish_reason)
            break

        # ── 3. Max rounds reached without stop ───────────────────────────────
        yield ChatStreamEvent(type="error", content="Agent loop reached max tool-use rounds")

    except Exception as exc:
        logger.error("agent_loop_error", error=str(exc), exc_info=exc)
        yield ChatStreamEvent(type="error", content=str(exc))
