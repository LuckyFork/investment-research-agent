"""Structured agent loop: decision planning → scene policy → optional tool → final answer."""

from typing import AsyncGenerator

from app.agents.orchestrator import apply_compliance_result, run_complex_task
from app.agent.query_classifier import classify_query, refine_query_analysis
from app.agent.decisioning import DECISION_PROMPT_VERSION, generate_answer_from_tool, plan_next_step
from app.agent.llm_client import PROMPT_VERSION
from app.agent.tools import ToolExecutionResult, execute_tool
from app.audit.service import record_audit_event
from app.compliance.checker import check_compliance
from app.compliance.rules import RULESET_VERSION
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.request_context import RequestContext
from app.memory.session import append_message, load_messages, load_summary
from app.models.chat import ChatMessage, ChatStreamEvent
from app.models.decision import ActionType, AgentDecision, RetrievalRoute
from app.policy.service import evaluate_agent_decision, evaluate_tool_call
from app.replay import save_trace, summarize_trace

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


def _tool_queries(decision: AgentDecision, user_message: str) -> list[str]:
    if decision.query_analysis.route == RetrievalRoute.MULTI_HOP_AGGREGATION:
        return decision.query_analysis.sub_queries or [decision.action.tool_args.get("query", user_message)]
    return [decision.action.tool_args.get("query", user_message)]


def _merge_tool_results(tool_outputs: list[tuple[str, str]]) -> str:
    if not tool_outputs:
        return ""
    if len(tool_outputs) == 1:
        return tool_outputs[0][1]

    parts: list[str] = []
    for idx, (query, result) in enumerate(tool_outputs, start=1):
        parts.append(f"[子查询 {idx}]\nquery: {query}\n{result}")
    return "\n\n".join(parts)


def _normalize_execution_result(result: str | ToolExecutionResult) -> ToolExecutionResult:
    if isinstance(result, ToolExecutionResult):
        return result
    return ToolExecutionResult(text=result)


async def _run_legacy_tool_flow(
    *,
    session_id: str,
    user_message: str,
    decision: AgentDecision,
    context: RequestContext,
    summary: str,
    settings,
) -> tuple[str, list[ChatStreamEvent]]:
    tool_name = decision.action.tool_name
    tool_args = decision.action.tool_args
    tool_queries = _tool_queries(decision, user_message)
    tool_outputs: list[tuple[str, str]] = []
    blocked_result = ""
    events: list[ChatStreamEvent] = []
    decision_fields = _decision_audit_fields(decision)

    for idx, query in enumerate(tool_queries, start=1):
        current_args = dict(tool_args)
        current_args["query"] = query
        tool_policy = evaluate_tool_call(tool_name, current_args, context)
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
            tool_args=current_args,
            policy_decision=tool_policy.model_dump(),
            message_preview=user_message,
            **decision_fields,
        )

        if tool_policy.allowed:
            query_label = tool_policy.sanitized_args.get("query", tool_name)
            if len(tool_queries) > 1:
                query_label = f"[{idx}/{len(tool_queries)}] {query_label}"
            events.append(
                ChatStreamEvent(
                    type="tool_start",
                    tool_name=tool_name,
                    content=query_label,
                )
            )
            raw_result = await execute_tool(tool_name, tool_policy.sanitized_args, context)
            execution_result = _normalize_execution_result(raw_result)
            result = execution_result.text
        else:
            result = tool_policy.user_message
            blocked_result = result
            execution_result = ToolExecutionResult(text=result)

        events.append(
            ChatStreamEvent(
                type="tool_done",
                tool_name=tool_name,
                content=result[:280],
                payload={
                    "query": current_args.get("query", ""),
                    "result_count": execution_result.result_count,
                    "top_score": execution_result.top_score,
                    "top_evidence": execution_result.evidences[0] if execution_result.evidences else {},
                },
            )
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
            tool_args=tool_policy.sanitized_args if tool_policy.allowed else current_args,
            tool_result_preview=result,
            policy_decision=tool_policy.model_dump(),
            **decision_fields,
        )

        if not tool_policy.allowed:
            break
        tool_outputs.append((query, result))

    if blocked_result:
        return blocked_result, events

    merged_result = _merge_tool_results(tool_outputs)
    full_reply = await generate_answer_from_tool(
        decision=decision,
        user_message=user_message,
        tool_result=merged_result,
        summary=summary,
    )
    return full_reply, events


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
        rule_based_analysis = classify_query(user_message)
        query_analysis = await refine_query_analysis(user_message, rule_based_analysis)
        decision = await plan_next_step(history, summary, query_analysis)
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
            if decision.query_analysis.route == RetrievalRoute.MULTI_HOP_AGGREGATION:
                try:
                    full_reply, task_trace, task_events = await run_complex_task(
                        session_id=session_id,
                        user_message=user_message,
                        decision=decision,
                        rule_analysis=rule_based_analysis,
                        context=context,
                        summary=summary,
                    )
                    for event in task_events:
                        yield event
                except Exception as exc:
                    logger.warning("complex_orchestration_fallback", error=str(exc))
                    full_reply, legacy_events = await _run_legacy_tool_flow(
                        session_id=session_id,
                        user_message=user_message,
                        decision=decision,
                        context=context,
                        summary=summary,
                        settings=settings,
                    )
                    for event in legacy_events:
                        yield event
            else:
                full_reply, legacy_events = await _run_legacy_tool_flow(
                    session_id=session_id,
                    user_message=user_message,
                    decision=decision,
                    context=context,
                    summary=summary,
                    settings=settings,
                )
                for event in legacy_events:
                    yield event
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
        if "task_trace" in locals():
            task_trace = apply_compliance_result(task_trace, cr)
            try:
                trace_path = save_trace(task_trace, settings.trace_output_dir)
                logger.info("task_trace_saved", trace_path=trace_path, trace_summary=summarize_trace(task_trace))
            except Exception as exc:
                logger.warning("task_trace_save_failed", error=str(exc))
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
