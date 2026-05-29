import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.query_classifier import classify_query, extract_query_features, refine_query_analysis, should_refine_query
from app.models.agent_task import AgentRole, ExecutionMode, TaskPlan, TaskRunTrace, TaskStatus, TaskStep
from app.models.chat import ChatStreamEvent
from app.core.request_context import RequestContext
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


def _decision(query_analysis: QueryAnalysis) -> AgentDecision:
    return AgentDecision(
        query_analysis=query_analysis,
        intent=IntentAssessment(
            intent_type=IntentType.RESEARCH_ANALYSIS,
            user_goal="分析问题",
            reasoning="测试 Adaptive-RAG 路由",
            confidence=0.94,
        ),
        action=ActionProposal(
            action_type=ActionType.SUMMARIZE_WITH_CITATIONS,
            requires_tool=True,
            tool_name="search_documents",
            tool_args={"query": "默认查询", "top_k": 5},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="",
        ),
        evidence=EvidenceBundle(
            citations=[],
            has_sufficient_evidence=False,
            evidence_gap="需要检索文档",
        ),
        response=ResponseDraft(
            answer_draft="",
            includes_risk_note=False,
            is_personalized=False,
            needs_human_review=False,
        ),
    )


class TestQueryClassifier:
    def test_extract_query_features_detects_summary_intent(self):
        features = extract_query_features("总结这份研报对营收增长的判断")
        assert features["has_summary_intent"] is True
        assert features["has_trend"] is True

    def test_classify_simple_query(self):
        analysis = classify_query("贵州茅台2024年营收是多少")
        assert analysis.complexity == QueryComplexity.SIMPLE
        assert analysis.route == RetrievalRoute.DIRECT_RETRIEVAL
        assert analysis.sub_queries == []
        assert analysis.source == "rule"

    def test_classify_summary_query(self):
        analysis = classify_query("总结这份研报对营收增长的判断")
        assert analysis.complexity == QueryComplexity.SUMMARY
        assert analysis.route == RetrievalRoute.SUMMARY_RETRIEVAL

    def test_classify_complex_query_with_sub_queries(self):
        analysis = classify_query("对比茅台和五粮液近两年营收和利润变化，并分析原因")
        assert analysis.complexity == QueryComplexity.COMPLEX
        assert analysis.route == RetrievalRoute.MULTI_HOP_AGGREGATION
        assert len(analysis.sub_queries) >= 2

    def test_should_refine_query_skips_short_simple_fact(self):
        analysis = classify_query("贵州茅台2024年营收是多少")
        assert should_refine_query(analysis) is False

    async def test_refine_query_analysis_accepts_high_confidence_llm_result(self):
        rule_based = classify_query("总结这份研报对营收增长的判断")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "complexity": "summary",
                "route": "summary_retrieval",
                "reasons": ["包含总结任务且需要引用文档"],
                "sub_queries": [],
                "confidence": 0.91,
            },
            ensure_ascii=False,
        )

        with patch("app.agent.query_classifier.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            refined = await refine_query_analysis("总结这份研报对营收增长的判断", rule_based)

        assert refined.source == "llm_refined"
        assert refined.confidence == 0.91
        assert refined.complexity == QueryComplexity.SUMMARY

    async def test_refine_query_analysis_falls_back_on_low_confidence(self):
        rule_based = classify_query("总结这份研报对营收增长的判断")
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "complexity": "summary",
                "route": "summary_retrieval",
                "reasons": ["模型判断不够确定"],
                "sub_queries": [],
                "confidence": 0.42,
            },
            ensure_ascii=False,
        )

        with patch("app.agent.query_classifier.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            refined = await refine_query_analysis("总结这份研报对营收增长的判断", rule_based)

        assert refined.source == "rule_fallback_low_confidence"
        assert refined.complexity == rule_based.complexity

    async def test_refine_query_analysis_guardrail_keeps_complex_query(self):
        query = "对比茅台和五粮液近两年营收和利润变化，并分析原因"
        rule_based = classify_query(query)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "complexity": "simple",
                "route": "direct_retrieval",
                "reasons": ["误判为简单问题"],
                "sub_queries": [],
                "confidence": 0.95,
            },
            ensure_ascii=False,
        )

        with patch("app.agent.query_classifier.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            refined = await refine_query_analysis(query, rule_based)

        assert refined.source == "rule_fallback_guardrail"
        assert refined.complexity == QueryComplexity.COMPLEX


class TestOrchestrationHarness:
    def test_build_task_plan_for_complex_query(self):
        from app.agents.orchestrator import build_task_plan

        decision = _decision(
            QueryAnalysis(
                complexity=QueryComplexity.COMPLEX,
                route=RetrievalRoute.MULTI_HOP_AGGREGATION,
                reasons=["包含多个分析对象"],
                sub_queries=["茅台近两年营收变化", "五粮液近两年营收变化", "两者差异原因"],
            )
        )

        task_plan = build_task_plan(
            "对比茅台和五粮液近两年营收和利润变化，并分析原因",
            decision,
        )

        assert task_plan.execution_mode == ExecutionMode.COMPLEX_ORCHESTRATED
        assert task_plan.steps[0].role == AgentRole.PLANNER
        assert [step.role for step in task_plan.steps].count(AgentRole.RETRIEVER) == 3
        assert task_plan.steps[-2].role == AgentRole.WRITER
        assert task_plan.steps[-1].role == AgentRole.COMPLIANCE

    async def test_run_complex_task_records_trace_and_events(self):
        from app.agents.orchestrator import run_complex_task

        decision = _decision(
            QueryAnalysis(
                complexity=QueryComplexity.COMPLEX,
                route=RetrievalRoute.MULTI_HOP_AGGREGATION,
                reasons=["包含多个分析对象"],
                sub_queries=["茅台近两年营收变化", "五粮液近两年营收变化"],
            )
        )

        with (
            patch("app.agents.retriever_agent.record_audit_event", new_callable=AsyncMock),
            patch("app.agents.retriever_agent.execute_tool", new_callable=AsyncMock, return_value="命中文档片段") as mock_execute,
            patch(
                "app.agents.writer_agent.generate_answer_from_tool",
                new_callable=AsyncMock,
                return_value="综合结论：两家公司表现存在差异。",
            ),
        ):
            answer, trace, events = await run_complex_task(
                session_id="sess-harness",
                user_message="对比茅台和五粮液近两年营收和利润变化，并分析原因",
                decision=decision,
                rule_analysis=decision.query_analysis,
                context=RequestContext(user_id="user-1", tenant_id="tenant-1"),
                summary="",
            )

        assert mock_execute.await_count == 2
        assert answer.startswith("综合结论")
        assert len([e for e in events if e.type == "tool_start"]) == 2
        retrieval_steps = [step for step in trace.step_results if step.role == AgentRole.RETRIEVER]
        assert all(step.status == TaskStatus.COMPLETED for step in retrieval_steps)
        writer_step = next(step for step in trace.step_results if step.role == AgentRole.WRITER)
        assert writer_step.status == TaskStatus.COMPLETED


class TestAdaptiveAgentLoop:
    async def test_multi_hop_route_executes_multiple_searches(self):
        from app.agent.agent_loop import run_agent

        decision = _decision(
            QueryAnalysis(
                complexity=QueryComplexity.COMPLEX,
                route=RetrievalRoute.MULTI_HOP_AGGREGATION,
                reasons=["包含多个分析对象"],
                sub_queries=["茅台近两年营收变化", "五粮液近两年营收变化", "两者差异原因"],
            )
        )

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.classify_query", return_value=decision.query_analysis),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock, return_value=decision.query_analysis),
            patch("app.agent.agent_loop.plan_next_step", new_callable=AsyncMock, return_value=decision),
            patch(
                "app.agent.agent_loop.run_complex_task",
                new_callable=AsyncMock,
                return_value=(
                    "综合结论：两家公司趋势存在差异。",
                    MagicMock(),
                    [
                        ChatStreamEvent(type="tool_start", tool_name="search_documents", content="[1/3] 茅台近两年营收变化"),
                        ChatStreamEvent(type="tool_done", tool_name="search_documents", content="命中文档片段"),
                        ChatStreamEvent(type="tool_start", tool_name="search_documents", content="[2/3] 五粮液近两年营收变化"),
                        ChatStreamEvent(type="tool_done", tool_name="search_documents", content="命中文档片段"),
                        ChatStreamEvent(type="tool_start", tool_name="search_documents", content="[3/3] 两者差异原因"),
                        ChatStreamEvent(type="tool_done", tool_name="search_documents", content="命中文档片段"),
                    ],
                ),
            ) as mock_harness,
            patch("app.agent.agent_loop.apply_compliance_result", return_value=MagicMock()),
        ):
            events = [
                e async for e in run_agent(
                    "sess-adaptive",
                    "对比茅台和五粮液近两年营收和利润变化，并分析原因",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        mock_harness.assert_awaited_once()
        tool_start_events = [e for e in events if e.type == "tool_start"]
        assert len(tool_start_events) == 3
        assert tool_start_events[0].content.startswith("[1/3]")

    async def test_complex_route_falls_back_to_legacy_flow_when_harness_fails(self):
        from app.agent.agent_loop import run_agent

        decision = _decision(
            QueryAnalysis(
                complexity=QueryComplexity.COMPLEX,
                route=RetrievalRoute.MULTI_HOP_AGGREGATION,
                reasons=["包含多个分析对象"],
                sub_queries=["茅台近两年营收变化", "五粮液近两年营收变化", "两者差异原因"],
            )
        )

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.classify_query", return_value=decision.query_analysis),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock, return_value=decision.query_analysis),
            patch("app.agent.agent_loop.plan_next_step", new_callable=AsyncMock, return_value=decision),
            patch("app.agent.agent_loop.run_complex_task", new_callable=AsyncMock, side_effect=RuntimeError("planner failed")),
            patch("app.agent.agent_loop.execute_tool", new_callable=AsyncMock, return_value="命中文档片段") as mock_execute,
            patch(
                "app.agent.agent_loop.generate_answer_from_tool",
                new_callable=AsyncMock,
                return_value="回退后的综合结论。",
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-fallback",
                    "对比茅台和五粮液近两年营收和利润变化，并分析原因",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        assert mock_execute.await_count == 3
        assert any(e.type == "text" for e in events)

    async def test_direct_route_executes_single_search(self):
        from app.agent.agent_loop import run_agent

        decision = _decision(
            QueryAnalysis(
                complexity=QueryComplexity.SIMPLE,
                route=RetrievalRoute.DIRECT_RETRIEVAL,
                reasons=["单事实查询"],
            )
        )
        decision.action = ActionProposal(
            action_type=ActionType.SEARCH_DOCUMENTS,
            requires_tool=True,
            tool_name="search_documents",
            tool_args={"query": "贵州茅台2024年营收"},
            fallback_action=ActionType.SAFE_REFUSAL,
            fallback_reason="",
        )

        with (
            patch("app.agent.agent_loop.load_messages", new_callable=AsyncMock, return_value=[]),
            patch("app.agent.agent_loop.load_summary", new_callable=AsyncMock, return_value=""),
            patch("app.agent.agent_loop.append_message", new_callable=AsyncMock),
            patch("app.agent.agent_loop.classify_query", return_value=decision.query_analysis),
            patch("app.agent.agent_loop.refine_query_analysis", new_callable=AsyncMock, return_value=decision.query_analysis),
            patch("app.agent.agent_loop.plan_next_step", new_callable=AsyncMock, return_value=decision),
            patch("app.agent.agent_loop.execute_tool", new_callable=AsyncMock, return_value="茅台2024年营收1700亿元") as mock_execute,
            patch(
                "app.agent.agent_loop.generate_answer_from_tool",
                new_callable=AsyncMock,
                return_value="根据文档，茅台2024年营收约1700亿元。",
            ),
        ):
            events = [
                e async for e in run_agent(
                    "sess-simple",
                    "贵州茅台2024年营收是多少",
                    RequestContext(user_id="user-1", tenant_id="tenant-1"),
                )
            ]

        assert mock_execute.await_count == 1
        assert any(e.type == "text" for e in events)
