from app.agent.decisioning import generate_answer_from_tool
from app.models.agent_task import TaskStatus, TaskStep
from app.models.decision import AgentDecision


def merge_tool_results(tool_outputs: list[tuple[str, str]]) -> str:
    if not tool_outputs:
        return ""
    if len(tool_outputs) == 1:
        return tool_outputs[0][1]

    parts: list[str] = []
    for idx, (query, result) in enumerate(tool_outputs, start=1):
        parts.append(f"[子查询 {idx}]\nquery: {query}\n{result}")
    return "\n\n".join(parts)


class WriterAgent:
    """Composes the final answer from aggregated retrieval evidence."""

    async def compose(
        self,
        *,
        step: TaskStep,
        decision: AgentDecision,
        user_message: str,
        tool_outputs: list[tuple[str, str]],
        summary: str,
    ) -> str:
        step.status = TaskStatus.RUNNING
        merged_result = merge_tool_results(tool_outputs)
        answer = await generate_answer_from_tool(
            decision=decision,
            user_message=user_message,
            tool_result=merged_result,
            summary=summary,
        )
        step.status = TaskStatus.COMPLETED
        step.output_payload = {"answer_preview": answer[:600]}
        return answer
