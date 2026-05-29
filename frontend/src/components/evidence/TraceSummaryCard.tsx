import { Link } from "react-router-dom";

import { TraceSummary } from "../../features/traces/types";
import { EmptyState } from "../common/EmptyState";
import { Badge } from "../common/Badge";
import { useI18n } from "../../i18n/provider";

export function TraceSummaryCard({ trace }: { trace: TraceSummary | null }) {
  const { t } = useI18n();

  if (!trace) {
    return <EmptyState title={t("empty.noTraceSummary")} body={t("empty.noTraceSummaryBody")} />;
  }

  return (
    <div className="space-y-4 rounded-2xl border border-line bg-white p-4 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge tone="accent">{t(`complexity.${trace.complexity}`)}</Badge>
        <Badge tone="warning">{t(`route.${trace.route}`)}</Badge>
        <Badge>{t("trace.stepCount", { count: trace.step_count })}</Badge>
      </div>
      <div>
        <p className="font-semibold text-text">{t("trace.traceId")}</p>
        <p className="font-mono text-xs text-muted">{trace.trace_id}</p>
      </div>
      <div>
        <p className="font-semibold text-text">{t("trace.answerPreview")}</p>
        <p className="mt-2 text-text">{trace.final_answer_preview || t("trace.noPreview")}</p>
      </div>
      {trace.fallback_triggered ? (
        <div className="rounded-xl border border-warning/20 bg-warning/10 p-3 text-warning">
          {t("trace.fallbackTriggered")}: {trace.fallback_reason || t("trace.unknownReason")}
        </div>
      ) : null}
      <Link
        to={`/traces/${trace.trace_id}`}
        className="inline-flex rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white"
      >
        {t("trace.viewFullTrace")}
      </Link>
    </div>
  );
}
