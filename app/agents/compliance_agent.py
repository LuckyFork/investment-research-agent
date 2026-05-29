from app.compliance.checker import check_compliance
from app.compliance.models import ComplianceResult
from app.models.agent_task import TaskStatus, TaskStep


class ComplianceAgent:
    """Wraps the final compliance review as an explicit agent role."""

    def review(self, *, step: TaskStep, answer: str) -> ComplianceResult:
        step.status = TaskStatus.RUNNING
        result = check_compliance(answer)
        step.status = TaskStatus.COMPLETED
        step.output_payload = {
            "passed": result.passed,
            "issues": [issue.model_dump() for issue in result.issues],
        }
        return result

    def record_existing_result(self, *, step: TaskStep, result: ComplianceResult) -> ComplianceResult:
        step.status = TaskStatus.COMPLETED
        step.output_payload = {
            "passed": result.passed,
            "issues": [issue.model_dump() for issue in result.issues],
        }
        return result
