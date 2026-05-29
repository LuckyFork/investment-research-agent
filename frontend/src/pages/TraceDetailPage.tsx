import { useParams } from "react-router-dom";

import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { QueryAnalysisCard } from "../components/execution/QueryAnalysisCard";
import { TaskPlanPanel } from "../components/execution/TaskPlanPanel";
import { AppShell } from "../components/layout/AppShell";
import { Panel } from "../components/layout/Panel";
import { useTraceDetail } from "../features/traces/hooks";
import { useI18n } from "../i18n/provider";

export function TraceDetailPage() {
  const { t } = useI18n();
  const { traceId = "" } = useParams();
  const { data, isLoading, error } = useTraceDetail(traceId);

  return (
    <AppShell>
      <div className="space-y-6">
        <Panel title={t("trace.traceHeader")}>
          {isLoading ? <LoadingState label={t("trace.loadingDetail")} /> : null}
          {error ? <ErrorState message={(error as Error).message} /> : null}
          {!isLoading && !error && !data ? (
            <EmptyState title={t("trace.traceNotFound")} body={t("trace.traceNotFoundBody")} />
          ) : null}
          {data ? (
            <div className="space-y-3 text-sm">
              <p className="font-display text-2xl font-semibold text-accent">{data.trace_id}</p>
              <p className="text-text">{data.query}</p>
              <p className="font-mono text-xs text-muted">{`${t("common.sessionId")}: ${data.session_id}`}</p>
            </div>
          ) : null}
        </Panel>

        {data ? (
          <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr_1fr]">
            <Panel title={t("trace.analysis")}>
              <QueryAnalysisCard analysis={data.refined_analysis} />
            </Panel>
            <Panel title={t("trace.taskSteps")}>
              <TaskPlanPanel trace={data} />
            </Panel>
            <Panel title={t("trace.evidenceAndAnswer")}>
              <EvidencePanel trace={data} />
              <div className="mt-5 rounded-2xl border border-line bg-white p-4 text-sm text-text">
                <p className="mb-2 font-semibold">{t("trace.finalAnswer")}</p>
                <p>{data.final_answer || t("trace.noAnswer")}</p>
              </div>
            </Panel>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
