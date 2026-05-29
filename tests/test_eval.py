import json
from unittest.mock import AsyncMock, patch

from app.core.request_context import RequestContext
from app.evals.models import EvalCase
from app.evals.runner import load_eval_cases, run_eval_case
from app.evals.scorer import score_case
from app.models.agent_task import (
    AgentRole,
    ExecutionMode,
    TaskPlan,
    TaskRunTrace,
    TaskStatus,
    TaskStep,
)
from app.models.chat import ChatStreamEvent
from app.models.decision import QueryAnalysis, QueryComplexity, RetrievalRoute


def _analysis() -> QueryAnalysis:
    return QueryAnalysis(
        complexity=QueryComplexity.COMPLEX,
        route=RetrievalRoute.MULTI_HOP_AGGREGATION,
        reasons=["多实体对比"],
        sub_queries=["茅台变化", "五粮液变化"],
    )


def _trace() -> TaskRunTrace:
    analysis = _analysis()
    plan = TaskPlan(
        query="对比问题",
        query_analysis=analysis,
        execution_mode=ExecutionMode.COMPLEX_ORCHESTRATED,
        steps=[
            TaskStep(
                step_id="retrieval_1",
                role=AgentRole.RETRIEVER,
                instruction="检索1",
                status=TaskStatus.COMPLETED,
                output_payload={"result_preview": "[1] 文档:doc-maotai  第12页  相关度:0.93\n营收片段"},
            ),
            TaskStep(
                step_id="writer",
                role=AgentRole.WRITER,
                instruction="写作",
                status=TaskStatus.COMPLETED,
            ),
        ],
    )
    return TaskRunTrace(
        trace_id="eval-trace",
        session_id="eval-session",
        query="对比问题",
        rule_analysis=analysis,
        refined_analysis=analysis,
        task_plan=plan,
        step_results=[step.model_copy(deep=True) for step in plan.steps],
        final_answer="综合结论：茅台和五粮液的营收与利润走势存在差异。",
        compliance_result={"passed": True, "issues": []},
        artifact_path="/tmp/eval-trace.json",
    )


class TestEvalLoader:
    def test_load_eval_cases(self, tmp_path):
        path = tmp_path / "cases.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "case-1",
                        "query": "贵州茅台2024年营收是多少",
                        "expected_route": "direct_retrieval",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cases = load_eval_cases(str(path))
        assert len(cases) == 1
        assert cases[0].id == "case-1"


class TestEvalScorer:
    def test_score_case_uses_trace_and_answer(self):
        case = EvalCase(
            id="case-2",
            query="对比问题",
            expected_complexity=QueryComplexity.COMPLEX,
            expected_route=RetrievalRoute.MULTI_HOP_AGGREGATION,
            expected_documents=["doc-maotai"],
            expected_pages=[12],
            must_include_terms=["茅台", "五粮液", "营收"],
            should_pass_compliance=True,
        )
        result = score_case(
            case=case,
            analysis=_analysis(),
            answer="综合结论：茅台和五粮液营收存在差异。",
            compliance_passed=True,
            trace=_trace(),
            trace_path="/tmp/eval-trace.json",
        )

        assert result.route_correct is True
        assert result.document_hit is True
        assert result.page_hit is True
        assert result.keyword_hit_ratio == 1.0
        assert result.compliance_correct is True


class TestEvalRunner:
    async def test_run_eval_case_scores_saved_trace(self):
        case = EvalCase(
            id="case-3",
            query="对比问题",
            expected_route=RetrievalRoute.MULTI_HOP_AGGREGATION,
            expected_documents=["doc-maotai"],
            expected_pages=[12],
            must_include_terms=["茅台", "五粮液", "营收"],
            should_pass_compliance=True,
        )

        async def _fake_run_agent(*args, **kwargs):
            yield ChatStreamEvent(type="compliance", compliance_passed=True, compliance_issues=[])
            yield ChatStreamEvent(type="text", content="综合结论：茅台和五粮液营收存在差异。")
            yield ChatStreamEvent(type="done", session_id="eval-case")

        with (
            patch("app.evals.runner.classify_query", return_value=_analysis()),
            patch("app.evals.runner.refine_query_analysis", new_callable=AsyncMock, return_value=_analysis()),
            patch("app.evals.runner.run_agent", side_effect=_fake_run_agent),
            patch("app.evals.runner.Path.exists", return_value=True),
            patch("app.evals.runner.load_trace", return_value=_trace()),
        ):
            result = await run_eval_case(
                case,
                session_id="eval-case",
                context=RequestContext(user_id="eval-user", tenant_id="eval-tenant", request_id="eval-case-3"),
            )

        assert result.route_correct is True
        assert result.document_hit is True
        assert result.page_hit is True
        assert result.compliance_correct is True
