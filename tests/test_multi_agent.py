from unittest.mock import AsyncMock, patch

from app.compliance.models import ComplianceResult
from app.core.request_context import RequestContext
from app.models.agent_task import AgentRole, TaskStatus, TaskStep
from app.models.decision import (
    ActionProposal,
    ActionType,
    AgentDecision,
    EvidenceBundle,
    IntentAssessment,
    IntentType,
    QueryAnalysis,
    QueryComplexity,
    ResponseDraft,
    RetrievalRoute,
)


def _decision() -> AgentDecision:
    return AgentDecision(
        query_analysis=QueryAnalysis(
            complexity=QueryComplexity.COMPLEX,
            route=RetrievalRoute.MULTI_HOP_AGGREGATION,
            reasons=["包含多个分析对象"],
            sub_queries=["茅台近两年营收变化", "五粮液近两年营收变化"],
        ),
        intent=IntentAssessment(
            intent_type=IntentType.RESEARCH_ANALYSIS,
            user_goal="对比分析",
            reasoning="测试 multi-agent",
            confidence=0.9,
        ),
        action=ActionProposal(
            action_type=ActionType.SUMMARIZE_WITH_CITATIONS,
            requires_tool=True,
            tool_name="search_documents",
            tool_args={"query": "默认查询", "top_k": 5},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="",
        ),
        evidence=EvidenceBundle(citations=[], has_sufficient_evidence=False, evidence_gap="需要检索"),
        response=ResponseDraft(answer_draft="", includes_risk_note=False, is_personalized=False),
    )


class TestPlannerAgent:
    def test_create_plan_contains_expected_roles(self):
        from app.agents.planner import PlannerAgent

        plan = PlannerAgent().create_plan("对比问题", _decision())
        roles = [step.role for step in plan.steps]
        assert roles[0] == AgentRole.PLANNER
        assert roles.count(AgentRole.RETRIEVER) == 2
        assert roles[-2] == AgentRole.WRITER
        assert roles[-1] == AgentRole.COMPLIANCE


class TestRetrieverAgent:
    async def test_run_step_executes_tool_and_updates_step(self):
        from app.agents.retriever_agent import RetrieverAgent

        step = TaskStep(
            step_id="retrieval_1",
            role=AgentRole.RETRIEVER,
            instruction="检索证据",
            input_payload={"query": "茅台近两年营收变化", "tool_name": "search_documents", "top_k": 5},
        )
        with (
            patch("app.agents.retriever_agent.record_audit_event", new_callable=AsyncMock),
            patch("app.agents.retriever_agent.execute_tool", new_callable=AsyncMock, return_value="命中文档片段"),
        ):
            result, events = await RetrieverAgent().run_step(
                step=step,
                step_index=1,
                total_steps=2,
                session_id="sess-1",
                user_message="对比问题",
                decision=_decision(),
                context=RequestContext(user_id="user-1", tenant_id="tenant-1"),
            )

        assert result == "命中文档片段"
        assert step.status == TaskStatus.COMPLETED
        assert step.output_payload["result_count"] == 0
        assert step.output_payload["evidences"] == []
        assert len(events) == 2
        assert events[0].type == "tool_start"
        assert events[1].type == "tool_done"
        assert events[1].payload["result_count"] == 0


class TestWriterAgent:
    async def test_compose_uses_evidence_bundle(self):
        from app.agents.writer_agent import WriterAgent

        step = TaskStep(step_id="writer", role=AgentRole.WRITER, instruction="写回答")
        with patch(
            "app.agents.writer_agent.generate_answer_from_tool",
            new_callable=AsyncMock,
            return_value="综合结论：两家公司存在差异。",
        ):
            answer = await WriterAgent().compose(
                step=step,
                decision=_decision(),
                user_message="对比问题",
                tool_outputs=[("茅台近两年营收变化", "片段1"), ("五粮液近两年营收变化", "片段2")],
                summary="",
            )

        assert answer.startswith("综合结论")
        assert step.status == TaskStatus.COMPLETED
        assert "answer_preview" in step.output_payload


class TestComplianceAgent:
    def test_record_existing_result_updates_step(self):
        from app.agents.compliance_agent import ComplianceAgent

        step = TaskStep(step_id="compliance", role=AgentRole.COMPLIANCE, instruction="合规检查")
        result = ComplianceResult(passed=True, issues=[])
        returned = ComplianceAgent().record_existing_result(step=step, result=result)

        assert returned.passed is True
        assert step.status == TaskStatus.COMPLETED
        assert step.output_payload["passed"] is True
