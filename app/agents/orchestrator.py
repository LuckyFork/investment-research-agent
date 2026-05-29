from app.agents.compliance_agent import ComplianceAgent
from app.agents.planner import PlannerAgent
from app.agents.retriever_agent import RetrieverAgent
from app.agents.writer_agent import WriterAgent
from app.compliance.models import ComplianceResult
from app.core.logging import get_logger
from app.core.request_context import RequestContext
from app.models.agent_task import (
    AgentRole,
    TaskPlan,
    TaskRunTrace,
    TaskStatus,
    TaskStep,
)
from app.models.chat import ChatStreamEvent
from app.models.decision import AgentDecision

logger = get_logger(__name__)

def build_task_plan(query: str, decision: AgentDecision) -> TaskPlan:
    return PlannerAgent().create_plan(query, decision)


def _trace_from_plan(
    *,
    session_id: str,
    context: RequestContext,
    user_message: str,
    rule_analysis,
    decision: AgentDecision,
    task_plan: TaskPlan,
) -> TaskRunTrace:
    return TaskRunTrace(
        trace_id=context.request_id,
        session_id=session_id,
        query=user_message,
        rule_analysis=rule_analysis,
        refined_analysis=decision.query_analysis,
        task_plan=task_plan,
        step_results=[step.model_copy(deep=True) for step in task_plan.steps],
    )


def _get_trace_step(trace: TaskRunTrace, step_id: str) -> TaskStep:
    for step in trace.step_results:
        if step.step_id == step_id:
            return step
    raise ValueError(f"Task step '{step_id}' not found in trace")


async def run_complex_task(
    *,
    session_id: str,
    user_message: str,
    decision: AgentDecision,
    rule_analysis,
    context: RequestContext,
    summary: str,
) -> tuple[str, TaskRunTrace, list[ChatStreamEvent]]:
    task_plan = build_task_plan(user_message, decision)
    trace = _trace_from_plan(
        session_id=session_id,
        context=context,
        user_message=user_message,
        rule_analysis=rule_analysis,
        decision=decision,
        task_plan=task_plan,
    )

    tool_name = decision.action.tool_name
    if not tool_name:
        raise ValueError("Complex orchestration requires a tool-backed decision")

    tool_outputs: list[tuple[str, str]] = []
    events: list[ChatStreamEvent] = []
    retrieval_steps = [step for step in trace.step_results if step.role == AgentRole.RETRIEVER]
    retriever = RetrieverAgent()
    writer = WriterAgent()

    for idx, step in enumerate(retrieval_steps, start=1):
        sub_query = str(step.input_payload.get("query", "")).strip()
        try:
            result, step_events = await retriever.run_step(
                step=step,
                step_index=idx,
                total_steps=len(retrieval_steps),
                session_id=session_id,
                user_message=user_message,
                decision=decision,
                context=context,
            )
        except Exception as exc:
            trace.fallback_triggered = True
            trace.fallback_reason = str(exc)
            raise
        events.extend(step_events)
        tool_outputs.append((sub_query, result))

    writer_step = _get_trace_step(trace, "writer")
    full_reply = await writer.compose(
        step=writer_step,
        decision=decision,
        user_message=user_message,
        tool_outputs=tool_outputs,
        summary=summary,
    )
    trace.final_answer = full_reply

    return full_reply, trace, events


def apply_compliance_result(trace: TaskRunTrace, result: ComplianceResult) -> TaskRunTrace:
    compliance_step = _get_trace_step(trace, "compliance")
    updated = ComplianceAgent().record_existing_result(step=compliance_step, result=result)
    trace.compliance_result = {
        "passed": updated.passed,
        "issues": [issue.model_dump() for issue in updated.issues],
    }
    return trace
