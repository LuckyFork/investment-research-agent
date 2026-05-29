const DOMAIN_TERMS = [
  "营收",
  "收入",
  "利润",
  "净利润",
  "毛利率",
  "增长",
  "增长驱动",
  "驱动因素",
  "高端产品",
  "渠道优化",
  "品牌力",
  "关键指标"
];

const NOISE_PHRASES = [
  "根据已上传文档",
  "根据文档",
  "请根据文档",
  "并简要说明",
  "主要",
  "有哪些",
  "是什么",
  "是多少",
  "多少",
  "问题",
  "文档"
];

function uniqueTerms(terms: string[]) {
  return Array.from(new Set(terms.filter((term) => term.trim().length >= 2))).sort(
    (left, right) => right.length - left.length
  );
}

export function extractHighlightTerms(query: string) {
  const terms: string[] = [];

  for (const match of query.match(/\b\d{4}年?\b/g) ?? []) {
    terms.push(match);
    terms.push(match.replace(/年$/, ""));
  }

  for (const term of DOMAIN_TERMS) {
    if (query.includes(term)) {
      terms.push(term);
    }
  }

  let normalized = query;
  for (const phrase of NOISE_PHRASES) {
    normalized = normalized.split(phrase).join(" ");
  }

  for (const segment of normalized.split(/[，。！？；、：\s]+/)) {
    const candidate = segment.trim();
    if (!candidate || candidate.length < 2) continue;
    if (candidate.length <= 12) {
      terms.push(candidate);
    }
    for (const chineseChunk of candidate.match(/[\u4e00-\u9fff]{2,8}/g) ?? []) {
      terms.push(chineseChunk);
    }
  }

  return uniqueTerms(terms).slice(0, 8);
}

export function buildHighlightedSegments(text: string, terms: string[]) {
  if (!terms.length) {
    return [{ text, highlighted: false }];
  }

  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern).filter(Boolean);

  return parts.map((part) => ({
    text: part,
    highlighted: terms.some((term) => term.toLowerCase() === part.toLowerCase())
  }));
}
