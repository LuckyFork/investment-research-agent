import { Badge } from "../common/Badge";
import { EmptyState } from "../common/EmptyState";
import { useI18n } from "../../i18n/provider";

type Props = {
  analysis: Record<string, unknown> | null;
};

export function QueryAnalysisCard({ analysis }: Props) {
  const { t } = useI18n();

  if (!analysis) {
    return <EmptyState title={t("empty.noQueryAnalysis")} body={t("empty.noQueryAnalysisBody")} />;
  }

  const reasons = (analysis.reasons as string[] | undefined) ?? [];
  const subQueries = (analysis.sub_queries as string[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Badge tone="accent">
          {String(analysis.complexity ? t(`complexity.${String(analysis.complexity)}`) : t("common.na"))}
        </Badge>
        <Badge tone="warning">{String(analysis.route ? t(`route.${String(analysis.route)}`) : "--")}</Badge>
        <Badge>{`${t("analysis.confidence")} ${Number(analysis.confidence ?? 0).toFixed(2)}`}</Badge>
        <Badge>{String(analysis.source ? t(`source.${String(analysis.source)}`) : t("analysis.unknown"))}</Badge>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">{t("analysis.reasons")}</p>
        <ul className="space-y-1 text-sm text-text">
          {reasons.length ? reasons.map((reason) => <li key={reason}>- {reason}</li>) : <li>- {t("analysis.noReasons")}</li>}
        </ul>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">{t("analysis.subQueries")}</p>
        <ul className="space-y-2 text-sm text-text">
          {subQueries.length ? subQueries.map((query) => <li key={query} className="rounded-xl bg-white px-3 py-2">{query}</li>) : <li>- {t("analysis.none")}</li>}
        </ul>
      </div>
    </div>
  );
}
