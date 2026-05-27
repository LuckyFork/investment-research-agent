from app.models.decision import ActionType, AgentDecision, IntentType
from app.core.request_context import RequestContext
from app.policy.models import PolicyDecision, ScenePolicyResult

MAX_SEARCH_TOP_K = 10
MAX_QUERY_LENGTH = 500
ALLOWED_TOOLS = {"search_documents"}


def evaluate_tool_call(name: str, args: dict, context: RequestContext) -> PolicyDecision:
    if not context.user_id or not context.tenant_id:
        return PolicyDecision(
            allowed=False,
            reason_code="CTX_001",
            reason="Missing authenticated request context",
            user_message="当前请求缺少身份上下文，系统已阻止工具调用。",
        )

    if name not in ALLOWED_TOOLS:
        return PolicyDecision(
            allowed=False,
            reason_code="TOOL_001",
            reason=f"Tool '{name}' is not in the policy allowlist",
            user_message="当前工具不在允许范围内，系统已阻止本次调用。",
        )

    if name == "search_documents":
        raw_query = str(args.get("query", "")).strip()
        if not raw_query:
            return PolicyDecision(
                allowed=False,
                reason_code="ARG_001",
                reason="search_documents requires a non-empty query",
                user_message="检索请求缺少有效 query，系统已阻止本次调用。",
            )

        if len(raw_query) > MAX_QUERY_LENGTH:
            raw_query = raw_query[:MAX_QUERY_LENGTH]

        raw_top_k = args.get("top_k", 5)
        try:
            top_k = int(raw_top_k)
        except (TypeError, ValueError):
            return PolicyDecision(
                allowed=False,
                reason_code="ARG_002",
                reason="top_k must be an integer",
                user_message="检索参数不合法，系统已阻止本次调用。",
            )

        top_k = max(1, min(top_k, MAX_SEARCH_TOP_K))

        return PolicyDecision(
            allowed=True,
            reason_code="ALLOW_001",
            reason="Read-only document search is allowed for authenticated users",
            user_message="",
            sanitized_args={
                "query": raw_query,
                "top_k": top_k,
            },
        )

    return PolicyDecision(
        allowed=False,
        reason_code="TOOL_999",
        reason="Unhandled tool name",
        user_message="系统未识别该工具，已阻止调用。",
    )


def evaluate_agent_decision(decision: AgentDecision, context: RequestContext) -> ScenePolicyResult:
    if not context.user_id or not context.tenant_id:
        return ScenePolicyResult(
            allowed=False,
            reason_code="SCENE_001",
            reason="Missing authenticated request context",
            user_message="当前请求缺少身份上下文，系统暂不处理。",
            final_action=ActionType.SAFE_REFUSAL,
        )

    intent = decision.intent.intent_type
    action = decision.action.action_type

    if intent in {
        IntentType.PERSONALIZED_ADVICE_REQUEST,
        IntentType.HIGH_RISK_REQUEST,
        IntentType.INVESTMENT_OPINION,
    }:
        return ScenePolicyResult(
            allowed=False,
            reason_code="SCENE_002",
            reason="Investment advice and high-risk recommendation requests are downgraded",
            user_message=(
                "当前请求涉及投资建议或高风险推荐。系统仅提供研究信息和风险解释，"
                "不直接给出个性化投资结论，请联系人工复核。"
            ),
            final_action=ActionType.HANDOFF_TO_HUMAN,
            requires_human_review=True,
        )

    if intent == IntentType.UNKNOWN:
        return ScenePolicyResult(
            allowed=False,
            reason_code="SCENE_003",
            reason="User intent is unclear",
            user_message="我需要先确认你的目标。请说明你是想查事实、做总结，还是分析某份文档。",
            final_action=ActionType.ASK_CLARIFYING_QUESTION,
        )

    if action in {ActionType.SEARCH_DOCUMENTS, ActionType.SUMMARIZE_WITH_CITATIONS}:
        return ScenePolicyResult(
            allowed=True,
            reason_code="SCENE_ALLOW_001",
            reason="Read-only retrieval is allowed for research workflows",
            final_action=action,
            allow_tool=True,
            requires_citations=action == ActionType.SUMMARIZE_WITH_CITATIONS,
        )

    if action == ActionType.ANSWER_DIRECTLY:
        if (
            intent == IntentType.DOCUMENT_SUMMARY
            and not decision.evidence.has_sufficient_evidence
        ):
            return ScenePolicyResult(
                allowed=False,
                reason_code="SCENE_004",
                reason="Document summary without sufficient evidence is not allowed",
                user_message="当前证据不足以直接给出文档总结，请先提供文档或让我先检索相关内容。",
                final_action=ActionType.ASK_CLARIFYING_QUESTION,
            )

        if decision.response.is_personalized:
            return ScenePolicyResult(
                allowed=False,
                reason_code="SCENE_005",
                reason="Personalized response detected in a non-advice workflow",
                user_message="系统检测到个性化表达倾向，已改为仅提供通用研究信息。",
                final_action=ActionType.SAFE_REFUSAL,
            )

        return ScenePolicyResult(
            allowed=True,
            reason_code="SCENE_ALLOW_002",
            reason="Direct answer is allowed for low-risk research workflows",
            final_action=action,
        )

    if action == ActionType.ASK_CLARIFYING_QUESTION:
        return ScenePolicyResult(
            allowed=True,
            reason_code="SCENE_ALLOW_003",
            reason="Clarifying question is always allowed",
            final_action=action,
        )

    return ScenePolicyResult(
        allowed=False,
        reason_code="SCENE_999",
        reason="Unhandled scene/action combination",
        user_message="当前场景暂不支持自动处理，请联系人工复核。",
        final_action=ActionType.HANDOFF_TO_HUMAN,
        requires_human_review=True,
    )
