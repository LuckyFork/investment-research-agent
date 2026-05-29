from app.agent.llm_client import PROMPT_VERSION
from app.agent.tools import execute_tool
from app.audit.service import record_audit_event
from app.compliance.rules import RULESET_VERSION
from app.core.config import get_settings
from app.core.request_context import RequestContext
from app.models.agent_task import TaskStatus, TaskStep
from app.models.chat import ChatStreamEvent
from app.models.decision import AgentDecision
from app.policy.service import evaluate_tool_call
from app.agent.tools import ToolExecutionResult


def _normalize_execution_result(result: str | ToolExecutionResult) -> ToolExecutionResult:
    if isinstance(result, ToolExecutionResult):
        return result
    return ToolExecutionResult(text=result)


class RetrieverAgent:
    """Executes one retrieval step and returns both result text and stream events."""

    async def run_step(
        self,
        *,
        step: TaskStep,
        step_index: int,
        total_steps: int,
        session_id: str,
        user_message: str,
        decision: AgentDecision,
        context: RequestContext,
    ) -> tuple[str, list[ChatStreamEvent]]:
        settings = get_settings()
        tool_name = str(step.input_payload.get("tool_name", "")).strip()
        query = str(step.input_payload.get("query", "")).strip()
        current_args = dict(decision.action.tool_args)
        current_args["query"] = query

        step.status = TaskStatus.RUNNING
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
            decision_payload=decision.model_dump(),
            intent_type=decision.intent.intent_type.value,
            action_type=decision.action.action_type.value,
            confidence=decision.intent.confidence,
            citations=[c.model_dump() for c in decision.evidence.citations],
            fallback_reason=decision.action.fallback_reason,
        )

        if not tool_policy.allowed:
            step.status = TaskStatus.FAILED
            step.error_message = tool_policy.user_message
            step.output_payload = {"blocked": True, "reason_code": tool_policy.reason_code}
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
                tool_args=current_args,
                tool_result_preview=tool_policy.user_message,
                policy_decision=tool_policy.model_dump(),
                decision_payload=decision.model_dump(),
                intent_type=decision.intent.intent_type.value,
                action_type=decision.action.action_type.value,
                confidence=decision.intent.confidence,
                citations=[c.model_dump() for c in decision.evidence.citations],
                fallback_reason=decision.action.fallback_reason,
            )
            raise ValueError(tool_policy.user_message)

        query_label = f"[{step_index}/{total_steps}] {query}"
        raw_result = await execute_tool(tool_name, tool_policy.sanitized_args, context)
        execution_result = _normalize_execution_result(raw_result)
        result = execution_result.text
        step.status = TaskStatus.COMPLETED
        step.output_payload = {
            "query": query,
            "tool_name": tool_name,
            "result_preview": result[:600],
            "result_count": execution_result.result_count,
            "top_score": execution_result.top_score,
            "evidences": execution_result.evidences,
        }

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
            tool_args=tool_policy.sanitized_args,
            tool_result_preview=result,
            policy_decision=tool_policy.model_dump(),
            decision_payload=decision.model_dump(),
            intent_type=decision.intent.intent_type.value,
            action_type=decision.action.action_type.value,
            confidence=decision.intent.confidence,
            citations=[c.model_dump() for c in decision.evidence.citations],
            fallback_reason=decision.action.fallback_reason,
        )

        return result, [
            ChatStreamEvent(type="tool_start", tool_name=tool_name, content=query_label),
            ChatStreamEvent(
                type="tool_done",
                tool_name=tool_name,
                content=result[:280],
                payload={
                    "query": query,
                    "result_count": execution_result.result_count,
                    "top_score": execution_result.top_score,
                    "top_evidence": execution_result.evidences[0] if execution_result.evidences else {},
                },
            ),
        ]
