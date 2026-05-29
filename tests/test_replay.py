from app.models.agent_task import (
    AgentRole,
    ExecutionMode,
    TaskPlan,
    TaskRunTrace,
    TaskStatus,
    TaskStep,
)
from app.models.decision import QueryAnalysis, QueryComplexity, RetrievalRoute
from app.replay import load_trace, save_trace, summarize_trace


def _trace() -> TaskRunTrace:
    analysis = QueryAnalysis(
        complexity=QueryComplexity.COMPLEX,
        route=RetrievalRoute.MULTI_HOP_AGGREGATION,
        reasons=["多实体对比"],
        sub_queries=["子查询A", "子查询B"],
    )
    plan = TaskPlan(
        query="对比问题",
        query_analysis=analysis,
        execution_mode=ExecutionMode.COMPLEX_ORCHESTRATED,
        steps=[
            TaskStep(step_id="planner", role=AgentRole.PLANNER, instruction="规划", status=TaskStatus.COMPLETED),
            TaskStep(
                step_id="retrieval_1",
                role=AgentRole.RETRIEVER,
                instruction="检索",
                status=TaskStatus.COMPLETED,
                output_payload={"result_preview": "[1] 文档:doc-a  第12页  相关度:0.9\n片段A"},
            ),
            TaskStep(step_id="writer", role=AgentRole.WRITER, instruction="写作", status=TaskStatus.COMPLETED),
            TaskStep(step_id="compliance", role=AgentRole.COMPLIANCE, instruction="合规", status=TaskStatus.COMPLETED),
        ],
    )
    return TaskRunTrace(
        trace_id="trace-001",
        session_id="session-001",
        query="对比问题",
        rule_analysis=analysis,
        refined_analysis=analysis,
        task_plan=plan,
        step_results=[step.model_copy(deep=True) for step in plan.steps],
        final_answer="综合结论：表现存在差异。",
        compliance_result={"passed": True, "issues": []},
    )


class TestReplayStore:
    def test_save_and_load_trace(self, tmp_path):
        trace = _trace()
        saved_path = save_trace(trace, str(tmp_path))
        loaded = load_trace(saved_path)

        assert loaded.trace_id == "trace-001"
        assert loaded.artifact_path == saved_path
        assert loaded.final_answer.startswith("综合结论")

    def test_summarize_trace(self):
        trace = _trace()
        summary = summarize_trace(trace)

        assert summary["complexity"] == "complex"
        assert summary["route"] == "multi_hop_aggregation"
        assert summary["compliance_passed"] is True
        assert summary["step_count"] == 4
