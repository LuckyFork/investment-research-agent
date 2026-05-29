import json
import re

from app.agent.query_decomposer import decompose_query
from app.agent.llm_client import get_llm_client
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.decision import QueryAnalysis, QueryComplexity, RetrievalRoute

logger = get_logger(__name__)

_COMPARISON_TERMS = ("对比", "比较", "相比", "区别", "差异")
_TREND_TERMS = ("趋势", "变化", "增长", "下降", "波动", "走势")
_CAUSAL_TERMS = ("为什么", "原因", "驱动因素", "影响因素", "导致")
_SUMMARY_TERMS = ("总结", "概括", "摘要", "提炼", "归纳", "梳理")
_METRIC_TERMS = ("营收", "收入", "利润", "净利润", "毛利率", "净利率", "现金流", "费用率", "roe")
_TIME_RE = re.compile(
    r"(近[一二两三四五六七八九十\d]+年|近[一二两三四五六七八九十\d]+季度?|"
    r"20\d{2}(?:[-~至到]20\d{2})?|20\d{2}年?|Q[1-4]|上半年|下半年)"
)
_MULTI_ENTITY_RE = re.compile(r"(对比|比较|相比).*(和|与|及|以及|、)|.+(和|与|及|以及|、).+")

_REFINEMENT_SYSTEM = """你是投研问答系统里的 query refinement 分类器。
你的任务是：基于用户问题和规则分类结果，输出更稳的查询复杂度判断。

只允许输出 JSON，不要输出 markdown。
必须遵守：
1. complexity 只能是 simple / summary / complex
2. route 只能是 direct_retrieval / summary_retrieval / multi_hop_aggregation
3. confidence 取值范围 0~1
4. 如果问题明显涉及对比、多实体、多指标、趋势或原因分析，不要降级为 simple
5. complex 问题最多输出 3 个 sub_queries

JSON schema:
{
  "complexity": "simple|summary|complex",
  "route": "direct_retrieval|summary_retrieval|multi_hop_aggregation",
  "reasons": ["string"],
  "sub_queries": ["string"],
  "confidence": 0.0
}"""


def _extract_json_payload(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in refinement response")
    return text[start:end + 1]


def _contains_any(query: str, terms: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return any(term.lower() in lowered for term in terms)


def extract_query_features(query: str) -> dict:
    metric_hits = [term for term in _METRIC_TERMS if term.lower() in query.lower()]
    features = {
        "has_comparison": _contains_any(query, _COMPARISON_TERMS),
        "has_trend": _contains_any(query, _TREND_TERMS),
        "has_causality": _contains_any(query, _CAUSAL_TERMS),
        "has_summary_intent": _contains_any(query, _SUMMARY_TERMS),
        "has_time_range": bool(_TIME_RE.search(query)),
        "has_multiple_entities": bool(_MULTI_ENTITY_RE.search(query)),
        "has_multiple_metrics": len(set(metric_hits)) >= 2,
        "query_length": len(query.strip()),
    }
    return features


def _score_query_complexity(features: dict) -> tuple[QueryComplexity, list[str]]:
    score = 0
    reasons: list[str] = []

    if features["has_comparison"]:
        score += 2
        reasons.append("包含比较意图")
    if features["has_trend"]:
        score += 2
        reasons.append("包含趋势分析需求")
    if features["has_causality"]:
        score += 2
        reasons.append("包含归因/原因分析需求")
    if features["has_time_range"]:
        score += 1
        reasons.append("包含时间范围约束")
    if features["has_multiple_entities"]:
        score += 2
        reasons.append("包含多个分析对象")
    if features["has_multiple_metrics"]:
        score += 1
        reasons.append("涉及多个财务指标")
    if features["query_length"] > 30:
        score += 1
        reasons.append("问题描述较长")

    if score >= 4:
        return QueryComplexity.COMPLEX, reasons
    if features["has_summary_intent"] or score >= 2:
        if features["has_summary_intent"]:
            reasons.append("包含总结/归纳需求")
        return QueryComplexity.SUMMARY, reasons
    return QueryComplexity.SIMPLE, reasons or ["单事实查询"]


def _rule_confidence(features: dict, complexity: QueryComplexity) -> float:
    if complexity == QueryComplexity.COMPLEX:
        strong_hits = sum(
            1 for key in ("has_comparison", "has_trend", "has_causality", "has_multiple_entities")
            if features.get(key)
        )
        return min(0.98, 0.72 + strong_hits * 0.06)
    if complexity == QueryComplexity.SUMMARY:
        return 0.78 if features.get("has_summary_intent") else 0.7
    if features.get("query_length", 0) <= 18:
        return 0.86
    return 0.8


def _route_for_complexity(complexity: QueryComplexity) -> RetrievalRoute:
    if complexity == QueryComplexity.COMPLEX:
        return RetrievalRoute.MULTI_HOP_AGGREGATION
    if complexity == QueryComplexity.SUMMARY:
        return RetrievalRoute.SUMMARY_RETRIEVAL
    return RetrievalRoute.DIRECT_RETRIEVAL


def _strong_complex_signals(features: dict) -> bool:
    return (
        features.get("has_multiple_entities", False)
        or features.get("has_comparison", False)
        or (features.get("has_trend", False) and features.get("has_causality", False))
        or (features.get("has_time_range", False) and features.get("has_multiple_metrics", False))
    )


def should_refine_query(rule_based: QueryAnalysis) -> bool:
    features = rule_based.extracted_features
    if rule_based.complexity != QueryComplexity.SIMPLE:
        return True
    return (
        features.get("query_length", 0) > 18
        or features.get("has_summary_intent", False)
        or features.get("has_trend", False)
        or features.get("has_causality", False)
        or features.get("has_comparison", False)
    )


def _apply_refinement_guardrails(
    query: str,
    rule_based: QueryAnalysis,
    refined: QueryAnalysis,
) -> QueryAnalysis:
    features = rule_based.extracted_features

    if refined.confidence < 0.6:
        fallback = rule_based.model_copy(deep=True)
        fallback.source = "rule_fallback_low_confidence"
        fallback.reasons = fallback.reasons + [f"LLM refinement confidence too low: {refined.confidence:.2f}"]
        return fallback

    if _strong_complex_signals(features) and refined.complexity == QueryComplexity.SIMPLE:
        fallback = rule_based.model_copy(deep=True)
        fallback.source = "rule_fallback_guardrail"
        fallback.reasons = fallback.reasons + ["后端 guardrail 保留复杂查询判定"]
        return fallback

    normalized = refined.model_copy(deep=True)
    normalized.route = _route_for_complexity(normalized.complexity)
    normalized.extracted_features = dict(features)
    normalized.source = "llm_refined"

    if normalized.complexity == QueryComplexity.COMPLEX:
        if not normalized.sub_queries:
            normalized.sub_queries = rule_based.sub_queries or decompose_query(query, features)
        normalized.sub_queries = normalized.sub_queries[:3]
    else:
        normalized.sub_queries = []

    if not normalized.reasons:
        normalized.reasons = rule_based.reasons
    return normalized


async def refine_query_analysis(query: str, rule_based: QueryAnalysis) -> QueryAnalysis:
    if not should_refine_query(rule_based):
        return rule_based

    settings = get_settings()
    prompt = json.dumps(
        {
            "query": query,
            "rule_based": rule_based.model_dump(),
        },
        ensure_ascii=False,
        indent=2,
    )

    try:
        response = await get_llm_client().chat.completions.create(
            model=settings.llm_model,
            max_tokens=800,
            messages=[
                {"role": "system", "content": _REFINEMENT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = json.loads(_extract_json_payload(content))
        refined = QueryAnalysis.model_validate(
            {
                **payload,
                "extracted_features": rule_based.extracted_features,
                "source": "llm_refined",
            }
        )
        return _apply_refinement_guardrails(query, rule_based, refined)
    except Exception as exc:
        logger.warning("query_refinement_fallback", error=str(exc), query=query[:80])
        fallback = rule_based.model_copy(deep=True)
        fallback.source = "rule_fallback_exception"
        fallback.reasons = fallback.reasons + ["LLM refinement failed, fallback to rule-based analysis"]
        return fallback


def classify_query(query: str) -> QueryAnalysis:
    features = extract_query_features(query)
    complexity, reasons = _score_query_complexity(features)
    route = _route_for_complexity(complexity)
    sub_queries = decompose_query(query, features) if complexity == QueryComplexity.COMPLEX else []
    return QueryAnalysis(
        complexity=complexity,
        route=route,
        reasons=reasons,
        extracted_features=features,
        sub_queries=sub_queries,
        confidence=_rule_confidence(features, complexity),
        source="rule",
    )
