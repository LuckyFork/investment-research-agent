import { EvalSummary } from "../../features/evals/types";
import { formatPercent } from "../../lib/format";
import { EmptyState } from "../common/EmptyState";
import { useI18n } from "../../i18n/provider";

export function EvalSummaryCards({ summary }: { summary: EvalSummary | undefined }) {
  const { t } = useI18n();

  if (!summary || !summary.total_cases) {
    return <EmptyState title={t("eval.noSummary")} body={t("eval.noSummaryBody")} />;
  }

  const items = [
    [t("eval.cards.cases"), String(summary.total_cases)],
    [t("eval.cards.route"), formatPercent(summary.route_accuracy)],
    [t("eval.cards.documentHit"), formatPercent(summary.document_hit_rate)],
    [t("eval.cards.pageHit"), formatPercent(summary.page_hit_rate)],
    [t("eval.cards.keywordHit"), formatPercent(summary.keyword_hit_rate)],
    [t("eval.cards.compliance"), formatPercent(summary.compliance_accuracy)]
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-2xl border border-line bg-white p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-muted">{label}</p>
          <p className="mt-3 font-display text-3xl font-semibold text-text">{value}</p>
        </div>
      ))}
    </div>
  );
}
