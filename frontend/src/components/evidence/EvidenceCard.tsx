import { useMemo, useState } from "react";

import { Badge } from "../common/Badge";
import type { EvidenceItem } from "../../features/traces/types";
import { buildHighlightedSegments, extractHighlightTerms } from "../../lib/highlight";
import { useI18n } from "../../i18n/provider";

function formatScore(score: number | null | undefined) {
  if (typeof score !== "number") return "n/a";
  return score.toFixed(4);
}

const COLLAPSED_LENGTH = 220;

export function EvidenceCard({
  evidence,
  index,
  query
}: {
  evidence: EvidenceItem;
  index: number;
  query: string;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const highlightTerms = useMemo(() => extractHighlightTerms(query), [query]);
  const isCollapsible = evidence.snippet.length > COLLAPSED_LENGTH;
  const visibleSnippet =
    !expanded && isCollapsible
      ? `${evidence.snippet.slice(0, COLLAPSED_LENGTH).trimEnd()}…`
      : evidence.snippet;
  const segments = useMemo(
    () => buildHighlightedSegments(visibleSnippet, highlightTerms),
    [visibleSnippet, highlightTerms]
  );

  return (
    <div className="rounded-2xl border border-line bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{`#${index}`}</Badge>
        <Badge>{evidence.document_id}</Badge>
        <Badge tone="warning">{t("tool.page", { page: evidence.page_num ?? "?" })}</Badge>
        {evidence.section_title ? <Badge tone="success">{evidence.section_title}</Badge> : null}
        <Badge>{t("tool.score", { score: formatScore(evidence.final_score ?? evidence.score) })}</Badge>
      </div>
      {highlightTerms.length ? (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
          {highlightTerms.map((term) => (
            <span key={term} className="rounded-full bg-accent/10 px-2 py-1 text-accent">
              {term}
            </span>
          ))}
        </div>
      ) : null}
      <p className="mt-3 whitespace-pre-wrap text-text">
        {segments.map((segment, segmentIndex) =>
          segment.highlighted ? (
            <mark
              key={`${segment.text}-${segmentIndex}`}
              className="rounded bg-warning/25 px-0.5 text-text"
            >
              {segment.text}
            </mark>
          ) : (
            <span key={`${segment.text}-${segmentIndex}`}>{segment.text}</span>
          )
        )}
      </p>
      {isCollapsible ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 inline-flex rounded-full border border-line bg-panel px-3 py-1 text-xs font-semibold text-accent transition hover:bg-accent/10"
        >
          {expanded ? t("evidence.collapse") : t("evidence.expand")}
        </button>
      ) : null}
    </div>
  );
}
