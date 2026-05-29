import re

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.request_context import RequestContext
from app.doc_pipeline.embedder import embed_texts
from app.core.qdrant_client import get_qdrant
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SCORE_THRESHOLD = 0.4
DEFAULT_CANDIDATE_MULTIPLIER = 3
MIN_CANDIDATE_POOL = 12

_TIME_RE = re.compile(
    r"(20\d{2}(?:年)?|Q[1-4]|近[一二两三四五六七八九十\d]+年|近[一二两三四五六七八九十\d]+季度?)"
)
_TOKEN_RE = re.compile(r"[A-Za-z]{2,}|\d{4}|[\u4e00-\u9fff]{2,8}")
_FINANCE_TERMS = (
    "营收", "收入", "利润", "净利润", "毛利率", "净利率", "现金流", "费用率",
    "同比", "环比", "增长", "下降", "财务", "经营", "风险", "公告", "研报",
)
_SECTION_PRIORITIES = ("财务", "经营", "业绩", "摘要", "风险", "盈利", "收入", "利润")
_STOPWORDS = {
    "请", "帮我", "一下", "看看", "分析", "总结", "概括", "提炼", "归纳", "说明",
    "原因", "为什么", "多少", "是什么", "如何", "情况", "表现", "趋势", "变化",
    "对比", "比较", "以及", "这份", "研报", "报告", "公告", "文档", "一下子",
}


def _extract_query_keywords(query: str) -> dict[str, list[str]]:
    times = list(dict.fromkeys(_TIME_RE.findall(query)))
    metrics = [term for term in _FINANCE_TERMS if term in query]

    generic_terms: list[str] = []
    for token in _TOKEN_RE.findall(query):
        normalized = token.strip()
        if len(normalized) < 2 or normalized in _STOPWORDS:
            continue
        if normalized in metrics or normalized in times:
            continue
        if normalized not in generic_terms:
            generic_terms.append(normalized)

    return {
        "times": times,
        "metrics": list(dict.fromkeys(metrics)),
        "terms": generic_terms[:8],
    }


def _metadata_bonus(query_keywords: dict[str, list[str]], section_title: str) -> float:
    if not section_title:
        return 0.0

    bonus = 0.0
    if any(keyword in section_title for keyword in query_keywords["metrics"]):
        bonus += 0.4
    if any(keyword in section_title for keyword in query_keywords["terms"]):
        bonus += 0.3
    if any(marker in section_title for marker in _SECTION_PRIORITIES):
        bonus += 0.2
    return min(1.0, bonus)


def _keyword_score(query_keywords: dict[str, list[str]], text: str, section_title: str = "") -> float:
    combined = f"{section_title}\n{text}"
    score = 0.0

    for term in query_keywords["terms"]:
        if term in combined:
            score += 0.18

    for metric in query_keywords["metrics"]:
        if metric in combined:
            score += 0.22

    for time_term in query_keywords["times"]:
        if time_term in combined:
            score += 0.16

    if query_keywords["terms"] and all(term in combined for term in query_keywords["terms"][:2]):
        score += 0.1
    return min(1.0, score)


def _rank_results(query: str, results: list[dict]) -> list[dict]:
    query_keywords = _extract_query_keywords(query)
    ranked: list[dict] = []
    for result in results:
        keyword_score = _keyword_score(
            query_keywords=query_keywords,
            text=result["text"],
            section_title=result["section_title"],
        )
        metadata_bonus = _metadata_bonus(query_keywords, result["section_title"])
        final_score = (
            0.65 * result["score"]
            + 0.25 * keyword_score
            + 0.10 * metadata_bonus
        )
        ranked.append(
            {
                **result,
                "keyword_score": round(keyword_score, 4),
                "metadata_bonus": round(metadata_bonus, 4),
                "final_score": round(final_score, 4),
            }
        )

    ranked.sort(key=lambda item: (item["final_score"], item["score"]), reverse=True)
    return ranked


async def _vector_recall(
    query: str,
    context: RequestContext,
    candidate_pool: int,
) -> list[dict]:
    settings = get_settings()

    query_vec = (await embed_texts([query]))[0]
    logger.info("qdrant_vector_recall", query=query[:80], candidate_pool=candidate_pool)

    response = await get_qdrant().query_points(
        collection_name=settings.qdrant_collection_docs,
        query=query_vec,
        limit=candidate_pool,
        score_threshold=SCORE_THRESHOLD,
        query_filter=Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=context.tenant_id)),
                FieldCondition(key="owner_user_id", match=MatchValue(value=context.user_id)),
            ]
        ),
        with_payload=True,
    )

    return [
        {
            "text": hit.payload.get("text", ""),
            "document_id": hit.payload.get("document_id", ""),
            "score": round(hit.score, 4),
            "chunk_index": hit.payload.get("chunk_index", 0),
            "page_num": hit.payload.get("page_num", 0),
            "section_title": hit.payload.get("section_title", ""),
        }
        for hit in response.points
    ]


async def search_documents(
    query: str,
    context: RequestContext,
    top_k: int = 5,
) -> list[dict]:
    """
    Hybrid retrieval v1:
      1. vector recall from Qdrant
      2. keyword + metadata rescoring
      3. rerank and return top_k
    """
    candidate_pool = max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, MIN_CANDIDATE_POOL)
    recalled = await _vector_recall(query=query, context=context, candidate_pool=candidate_pool)
    if not recalled:
        logger.info("hybrid_search_done", hits=0, query=query[:80])
        return []

    ranked = _rank_results(query, recalled)
    final_results = ranked[:top_k]
    logger.info(
        "hybrid_search_done",
        hits=len(final_results),
        candidate_pool=len(recalled),
        query=query[:80],
    )
    return final_results


async def search_documents_multi(
    queries: list[str],
    context: RequestContext,
    top_k: int = 5,
) -> list[dict]:
    """Run multiple scoped retrievals and annotate which sub-query produced each hit."""
    merged: list[dict] = []
    for query in queries:
        results = await search_documents(query=query, context=context, top_k=top_k)
        for result in results:
            merged.append({"source_query": query, **result})
    return merged
