"""Structured agent loop: decision planning → scene policy → optional tool → final answer."""

from typing import AsyncGenerator

from app.agent.decisioning import DECISION_PROMPT_VERSION, generate_answer_from_tool, plan_next_step
from app.agent.llm_client import PROMPT_VERSION
from app.agent.tools import execute_tool
from app.audit.service import record_audit_event
from app.compliance.checker import check_compliance
from app.compliance.rules import RULESET_VERSION
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.request_context import RequestContext
from app.memory.session import append_message, load_messages, load_summary
from app.models.chat import ChatMessage, ChatStreamEvent
from app.models.decision import ActionType, AgentDecision
from app.policy.service import evaluate_agent_decision, evaluate_tool_call

logger = get_logger(__name__)

COMPLIANCE_BLOCK_MESSAGE = (
    "当前回答触发合规保护，系统已停止直接返回原始内容。"
    "请改为提问信息检索、事实核对类问题，或联系人工复核。"
)


def _decision_audit_fields(decision: AgentDecision) -> dict:
    return {
        "decision_payload": decision.model_dump(),
        "intent_type": decision.intent.intent_type.value,
        "action_type": decision.action.action_type.value,
        "confidence": decision.intent.confidence,
        "citations": [c.model_dump() for c in decision.evidence.citations],
        "fallback_reason": decision.action.fallback_reason,
    }


async def run_agent(
    session_id: str,
    user_message: str,
    context: RequestContext,
) -> AsyncGenerator[ChatStreamEvent, None]:
    """
    Full agentic cycle — yields ChatStreamEvent objects:
      compliance  → rule-based gate result for final text
      tool_start  → model decided to call a tool
      tool_done   → tool returned its result
      text        → final visible reply chunk(s)
      done        → conversation turn complete
      error       → unhandled exception during the loop
    """
    settings = get_settings()

    # ── 1. Load history, summary, and append user message ────────────────────
    history, summary = await load_messages(session_id), await load_summary(session_id)
    user_msg = ChatMessage(role="user", content=user_message)
    await append_message(session_id, user_msg)
    history.append(user_msg)
    await record_audit_event(
        trace_id=context.request_id,
        session_id=session_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        channel=context.channel,
        event_type="user_message",
        model_version=settings.llm_model,
        prompt_version=PROMPT_VERSION,
        rule_version=RULESET_VERSION,
        message_preview=user_message,
    )

    try:
        # ── 2. Planning pass: model outputs a structured decision ─────────────
        decision = await plan_next_step(history, summary)
        decision_fields = _decision_audit_fields(decision)
        await record_audit_event(
            trace_id=context.request_id,
            session_id=session_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            channel=context.channel,
            event_type="decision",
            model_version=settings.llm_model,
            prompt_version=DECISION_PROMPT_VERSION,
            rule_version=RULESET_VERSION,
            message_preview=user_message,
            **decision_fields,
        )

        # ── 3. Scene-level policy evaluates the structured decision ───────────
        scene_policy = evaluate_agent_decision(decision, context)
        await record_audit_event(
            trace_id=context.request_id,
            session_id=session_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            channel=context.channel,
            event_type="scene_policy",
            model_version=settings.llm_model,
            prompt_version=DECISION_PROMPT_VERSION,
            rule_version=RULESET_VERSION,
            policy_decision=scene_policy.model_dump(),
            message_preview=user_message,
            **decision_fields,
        )

        full_reply = ""

        # ── 4. Execute allowed path: direct answer, clarification, or retrieval ──
        if not scene_policy.allowed:
            full_reply = scene_policy.user_message or decision.response.answer_draft
        elif (
            scene_policy.allow_tool
            and decision.action.requires_tool
            and decision.action.tool_name
        ):
            tool_name = decision.action.tool_name
            tool_args = decision.action.tool_args
            tool_policy = evaluate_tool_call(tool_name, tool_args, context)
            await record_audit_event(
                trace_id=context.request_id,
                session_id=session_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                channel=context.channel,
                event_type="tool_call",
                model_version=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                rule_version=RULESET_VERSION,
                tool_name=tool_name,
                tool_args=tool_args,
                policy_decision=tool_policy.model_dump(),
                message_preview=user_message,
                **decision_fields,
            )

            if tool_policy.allowed:
                yield ChatStreamEvent(
                    type="tool_start",
                    tool_name=tool_name,
                    content=tool_policy.sanitized_args.get("query", tool_name),
                )
                result = await execute_tool(tool_name, tool_policy.sanitized_args, context)
            else:
                result = tool_policy.user_message

            yield ChatStreamEvent(
                type="tool_done",
                tool_name=tool_name,
                content=result[:600],
            )
            await record_audit_event(
                trace_id=context.request_id,
                session_id=session_id,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                channel=context.channel,
                event_type="tool_result",
                model_version=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                rule_version=RULESET_VERSION,
                tool_name=tool_name,
                tool_args=tool_policy.sanitized_args if tool_policy.allowed else tool_args,
                tool_result_preview=result,
                policy_decision=tool_policy.model_dump(),
                **decision_fields,
            )

            if tool_policy.allowed:
                full_reply = await generate_answer_from_tool(
                    decision=decision,
                    user_message=user_message,
                    tool_result=result,
                    summary=summary,
                )
            else:
                full_reply = result
        else:
            if scene_policy.final_action in {
                ActionType.ANSWER_DIRECTLY,
                ActionType.ASK_CLARIFYING_QUESTION,
            }:
                full_reply = decision.response.answer_draft
            else:
                full_reply = scene_policy.user_message or decision.response.answer_draft

        # ── 5. Final compliance gate and user-visible output ──────────────────
        cr = check_compliance(full_reply)
        yield ChatStreamEvent(
            type="compliance",
            compliance_passed=cr.passed,
            compliance_issues=[i.model_dump() for i in cr.issues],
        )
        await record_audit_event(
            trace_id=context.request_id,
            session_id=session_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            channel=context.channel,
            event_type="final_response",
            model_version=settings.llm_model,
            prompt_version=PROMPT_VERSION,
            rule_version=RULESET_VERSION,
            compliance_passed=cr.passed,
            compliance_issues=[i.model_dump() for i in cr.issues],
            message_preview=full_reply,
            policy_decision=scene_policy.model_dump(),
            **decision_fields,
        )

        if not cr.passed:
            assistant_msg = ChatMessage(role="assistant", content=COMPLIANCE_BLOCK_MESSAGE)
            await append_message(session_id, assistant_msg)
            yield ChatStreamEvent(type="text", content=COMPLIANCE_BLOCK_MESSAGE)
            yield ChatStreamEvent(type="done", session_id=session_id)
            return

        assistant_msg = ChatMessage(role="assistant", content=full_reply)
        await append_message(session_id, assistant_msg)
        yield ChatStreamEvent(type="text", content=full_reply)
        yield ChatStreamEvent(type="done", session_id=session_id)
        return

    except Exception as exc:
        logger.error("agent_loop_error", error=str(exc), exc_info=exc)
        await record_audit_event(
            trace_id=context.request_id,
            session_id=session_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            channel=context.channel,
            event_type="error",
            model_version=settings.llm_model,
            prompt_version=PROMPT_VERSION,
            rule_version=RULESET_VERSION,
            message_preview=user_message,
            error_message=str(exc),
        )
        yield ChatStreamEvent(type="error", content=str(exc))
