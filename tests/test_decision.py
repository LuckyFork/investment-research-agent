import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.decisioning import generate_answer_from_tool, plan_next_step
from app.models.chat import ChatMessage
from app.models.decision import ActionType, IntentType, QueryAnalysis, QueryComplexity, RetrievalRoute


class TestDecisionPlanning:
    async def test_plan_next_step_parses_json_object(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "intent": {
                    "intent_type": "fact_lookup",
                    "user_goal": "查茅台营收",
                    "reasoning": "用户在询问具体事实",
                    "confidence": 0.95,
                },
                "action": {
                    "action_type": "search_documents",
                    "requires_tool": True,
                    "tool_name": "search_documents",
                    "tool_args": {"query": "茅台营收", "top_k": 3},
                    "fallback_action": "safe_refusal",
                    "fallback_reason": "",
                },
                "evidence": {
                    "citations": [],
                    "has_sufficient_evidence": False,
                    "evidence_gap": "需要检索文档",
                },
                "response": {
                    "answer_draft": "我先帮你查文档。",
                    "includes_risk_note": False,
                    "is_personalized": False,
                    "needs_human_review": False,
                },
            },
            ensure_ascii=False,
        )

        with patch("app.agent.decisioning.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            decision = await plan_next_step(
                [ChatMessage(role="user", content="茅台营收多少")],
                "",
                QueryAnalysis(
                    complexity=QueryComplexity.SIMPLE,
                    route=RetrievalRoute.DIRECT_RETRIEVAL,
                    reasons=["单事实查询"],
                ),
            )

        assert decision.intent.intent_type == IntentType.FACT_LOOKUP
        assert decision.action.action_type == ActionType.SEARCH_DOCUMENTS
        assert decision.action.tool_args["query"] == "茅台营收"
        assert decision.query_analysis.route == RetrievalRoute.DIRECT_RETRIEVAL

    async def test_generate_answer_from_tool_returns_llm_text(self):
        from app.models.decision import (
            ActionProposal,
            AgentDecision,
            EvidenceBundle,
            IntentAssessment,
            ResponseDraft,
        )

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "根据文档，茅台2024年营收约1700亿元。"
        decision = AgentDecision(
            intent=IntentAssessment(
                intent_type=IntentType.FACT_LOOKUP,
                user_goal="查营收",
                reasoning="需要文档依据",
                confidence=0.9,
            ),
            action=ActionProposal(
                action_type=ActionType.SEARCH_DOCUMENTS,
                requires_tool=True,
                tool_name="search_documents",
                tool_args={"query": "茅台营收"},
                fallback_action=ActionType.SAFE_REFUSAL,
                fallback_reason="",
            ),
            evidence=EvidenceBundle(citations=[], has_sufficient_evidence=False, evidence_gap=""),
            response=ResponseDraft(answer_draft="", includes_risk_note=False, is_personalized=False),
        )

        with patch("app.agent.decisioning.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            answer = await generate_answer_from_tool(
                decision=decision,
                user_message="茅台营收多少",
                tool_result="[1] 文档:doc-1 第1页 相关度:0.9\n营收1700亿元",
            )

        assert "1700亿元" in answer

    async def test_plan_next_step_normalizes_unsupported_tool_name(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            {
                "intent": {
                    "intent_type": "research_analysis",
                    "user_goal": "分析茅台增长驱动",
                    "reasoning": "需要查文档后分析",
                    "confidence": 0.88,
                },
                "action": {
                    "action_type": "summarize_with_citations",
                    "requires_tool": True,
                    "tool_name": "document_retriever_and_analyzer",
                    "tool_args": {"top_k": 4},
                    "fallback_action": "safe_refusal",
                    "fallback_reason": "",
                },
                "evidence": {
                    "citations": [],
                    "has_sufficient_evidence": False,
                    "evidence_gap": "需要先检索资料",
                },
                "response": {
                    "answer_draft": "我先检索并整理证据。",
                    "includes_risk_note": False,
                    "is_personalized": False,
                    "needs_human_review": False,
                },
            },
            ensure_ascii=False,
        )

        with patch("app.agent.decisioning.get_llm_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            decision = await plan_next_step(
                [ChatMessage(role="user", content="分析贵州茅台2024年营收增长驱动")],
                "",
                QueryAnalysis(
                    complexity=QueryComplexity.COMPLEX,
                    route=RetrievalRoute.MULTI_HOP_AGGREGATION,
                    reasons=["需要多步检索和综合分析"],
                ),
            )

        assert decision.action.tool_name == "search_documents"
        assert decision.action.requires_tool is True
        assert decision.action.tool_args["query"] == "分析贵州茅台2024年营收增长驱动"
        assert decision.action.tool_args["top_k"] == 4
