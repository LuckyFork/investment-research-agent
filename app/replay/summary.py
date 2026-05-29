from app.models.agent_task import TaskRunTrace, TaskStatus


def summarize_trace(trace: TaskRunTrace) -> dict:
    failed_steps = [step.step_id for step in trace.step_results if step.status == TaskStatus.FAILED]
    completed_steps = [step.step_id for step in trace.step_results if step.status == TaskStatus.COMPLETED]
    return {
        "trace_id": trace.trace_id,
        "session_id": trace.session_id,
        "query": trace.query,
        "complexity": trace.refined_analysis.complexity.value,
        "route": trace.refined_analysis.route.value,
        "step_count": len(trace.step_results),
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "fallback_triggered": trace.fallback_triggered,
        "fallback_reason": trace.fallback_reason,
        "compliance_passed": trace.compliance_result.get("passed"),
        "final_answer_preview": trace.final_answer[:200],
        "artifact_path": trace.artifact_path,
    }
