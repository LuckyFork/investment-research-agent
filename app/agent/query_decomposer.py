import re


_COMPARISON_PREFIX_RE = re.compile(r"^(请|帮我|麻烦)?(对比|比较|分析|看看)?")
_TIME_TOKEN_RE = re.compile(
    r"(近[一二两三四五六七八九十\d]+年|近[一二两三四五六七八九十\d]+季度?|"
    r"20\d{2}(?:[-~至到]20\d{2})?|20\d{2}年?|Q[1-4]|上半年|下半年)"
)
_ENTITY_SPLIT_RE = re.compile(r"(?:和|与|及|以及|、)")
_TAIL_NOISE_RE = re.compile(
    r"(近[一二两三四五六七八九十\d]+年.*|营收.*|利润.*|毛利率.*|净利率.*|现金流.*|"
    r"变化.*|趋势.*|原因.*|影响因素.*|表现.*)$"
)


def _extract_time_phrase(query: str) -> str:
    matches = _TIME_TOKEN_RE.findall(query)
    return " ".join(dict.fromkeys(matches))


def _extract_metric_phrase(query: str) -> str:
    metrics = [term for term in ("营收", "收入", "利润", "净利润", "毛利率", "净利率", "现金流") if term in query]
    if not metrics:
        return "关键指标"
    return "、".join(dict.fromkeys(metrics))


def _extract_entities(query: str) -> list[str]:
    first_clause = re.split(r"[，。；,;]|并", query, maxsplit=1)[0]
    first_clause = _COMPARISON_PREFIX_RE.sub("", first_clause).strip()
    parts = _ENTITY_SPLIT_RE.split(first_clause)
    entities: list[str] = []
    for part in parts:
        entity = _TAIL_NOISE_RE.sub("", part).strip(" ：:，,。.；;")
        if len(entity) >= 2 and entity not in entities:
            entities.append(entity)
    return entities[:2]


def decompose_query(query: str, features: dict) -> list[str]:
    """Produce a small, deterministic sub-query plan for complex questions."""
    sub_queries: list[str] = []
    time_phrase = _extract_time_phrase(query)
    metric_phrase = _extract_metric_phrase(query)
    entities = _extract_entities(query)

    if features.get("has_multiple_entities") and entities:
        for entity in entities:
            parts = [entity]
            if time_phrase:
                parts.append(time_phrase)
            parts.append(f"{metric_phrase}变化与表现")
            sub_queries.append(" ".join(parts))
        sub_queries.append(query)
    else:
        trimmed = query.replace("为什么", "").replace("原因是什么", "").strip()
        if trimmed and trimmed != query:
            sub_queries.append(trimmed)
        sub_queries.append(query)

    deduped: list[str] = []
    for sub_query in sub_queries:
        normalized = " ".join(sub_query.split())
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped[:3]
