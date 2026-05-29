from enum import Enum

from pydantic import BaseModel, Field

from app.models.decision import QueryAnalysis


class AgentRole(str, Enum):
    PLANNER = "planner"
    RETRIEVER = "retriever"
    WRITER = "writer"
    COMPLIANCE = "compliance"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    FALLBACK = "fallback"


class ExecutionMode(str, Enum):
    COMPLEX_ORCHESTRATED = "complex_orchestrated"
    LEGACY_FALLBACK = "legacy_fallback"


class TaskStep(BaseModel):
    step_id: str
    role: AgentRole
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    input_payload: dict = Field(default_factory=dict)
    output_payload: dict = Field(default_factory=dict)
    error_message: str = ""


class TaskPlan(BaseModel):
    query: str
    query_analysis: QueryAnalysis
    execution_mode: ExecutionMode = ExecutionMode.COMPLEX_ORCHESTRATED
    steps: list[TaskStep] = Field(default_factory=list)
    fallback_strategy: str = "legacy_multi_hop_aggregation"


class TaskRunTrace(BaseModel):
    trace_id: str
    session_id: str
    query: str
    rule_analysis: QueryAnalysis
    refined_analysis: QueryAnalysis
    task_plan: TaskPlan
    step_results: list[TaskStep] = Field(default_factory=list)
    final_answer: str = ""
    compliance_result: dict = Field(default_factory=dict)
    fallback_triggered: bool = False
    fallback_reason: str = ""
    artifact_path: str = ""
