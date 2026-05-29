import json

from app.models.agent_task import (
    AgentRole,
    ExecutionMode,
    TaskPlan,
    TaskRunTrace,
    TaskStatus,
    TaskStep,
)
from app.models.decision import QueryAnalysis, QueryComplexity, RetrievalRoute


def _trace_dict(session_id: str, trace_id: str) -> dict:
    analysis = QueryAnalysis(
        complexity=QueryComplexity.COMPLEX,
        route=RetrievalRoute.MULTI_HOP_AGGREGATION,
        reasons=["multi-hop"],
        sub_queries=["a", "b"],
    )
    plan = TaskPlan(
        query="complex query",
        query_analysis=analysis,
        execution_mode=ExecutionMode.COMPLEX_ORCHESTRATED,
        steps=[
            TaskStep(step_id="planner", role=AgentRole.PLANNER, instruction="plan", status=TaskStatus.COMPLETED),
            TaskStep(step_id="writer", role=AgentRole.WRITER, instruction="write", status=TaskStatus.COMPLETED),
        ],
    )
    trace = TaskRunTrace(
        trace_id=trace_id,
        session_id=session_id,
        query="complex query",
        rule_analysis=analysis,
        refined_analysis=analysis,
        task_plan=plan,
        step_results=[step.model_copy(deep=True) for step in plan.steps],
        final_answer="answer",
        compliance_result={"passed": True, "issues": []},
        artifact_path="",
    )
    return trace.model_dump(mode="json")


class TestTraceApis:
    async def test_list_and_fetch_trace(self, client, auth_headers, tmp_path):
        from app.main import app

        app.dependency_overrides = {}
        from app.core.config import get_settings

        settings = get_settings()
        original = settings.trace_output_dir
        settings.trace_output_dir = str(tmp_path)
        try:
            trace_path = tmp_path / "req-1.json"
            trace_path.write_text(
                json.dumps(_trace_dict("tenant-1:user-1:s1", "req-1"), ensure_ascii=False),
                encoding="utf-8",
            )

            list_resp = await client.get("/api/v1/traces", headers=auth_headers)
            assert list_resp.status_code == 200
            items = list_resp.json()["data"]
            assert len(items) == 1
            assert items[0]["trace_id"] == "req-1"

            detail_resp = await client.get("/api/v1/traces/req-1", headers=auth_headers)
            assert detail_resp.status_code == 200
            assert detail_resp.json()["data"]["trace_id"] == "req-1"

            summary_resp = await client.get("/api/v1/traces/req-1/summary", headers=auth_headers)
            assert summary_resp.status_code == 200
            assert summary_resp.json()["data"]["route"] == "multi_hop_aggregation"

            latest_resp = await client.get("/api/v1/traces/sessions/s1/latest", headers=auth_headers)
            assert latest_resp.status_code == 200
            assert latest_resp.json()["data"]["trace_id"] == "req-1"
        finally:
            settings.trace_output_dir = original


class TestEvalApis:
    async def test_read_latest_eval_artifacts(self, client, auth_headers, tmp_path):
        from app.core.config import get_settings

        settings = get_settings()
        original = settings.eval_output_dir
        settings.eval_output_dir = str(tmp_path)
        try:
            (tmp_path / "latest-summary.json").write_text(
                json.dumps({"total_cases": 3, "route_accuracy": 1.0}, ensure_ascii=False),
                encoding="utf-8",
            )
            (tmp_path / "latest-details.json").write_text(
                json.dumps([{"case_id": "case-1", "route_correct": True}], ensure_ascii=False),
                encoding="utf-8",
            )

            summary_resp = await client.get("/api/v1/evals/latest-summary", headers=auth_headers)
            assert summary_resp.status_code == 200
            assert summary_resp.json()["data"]["total_cases"] == 3

            details_resp = await client.get("/api/v1/evals/latest-details", headers=auth_headers)
            assert details_resp.status_code == 200
            assert details_resp.json()["data"][0]["case_id"] == "case-1"
        finally:
            settings.eval_output_dir = original
