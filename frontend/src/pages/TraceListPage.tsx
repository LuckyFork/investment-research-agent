import { Link } from "react-router-dom";

import { AppShell } from "../components/layout/AppShell";
import { Panel } from "../components/layout/Panel";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { EmptyState } from "../components/common/EmptyState";
import { useTraceList } from "../features/traces/hooks";
import { formatTime } from "../lib/format";
import { useI18n } from "../i18n/provider";

export function TraceListPage() {
  const { t } = useI18n();
  const { data, isLoading, error } = useTraceList();

  return (
    <AppShell>
      <Panel title={t("trace.recentTraces")}>
        {isLoading ? <LoadingState label={t("trace.loadingSummaries")} /> : null}
        {error ? <ErrorState message={(error as Error).message} /> : null}
        {!isLoading && !error && !data?.length ? (
          <EmptyState title={t("trace.noTraces")} body={t("trace.noTracesBody")} />
        ) : null}
        <div className="space-y-4">
          {data?.map((trace) => (
            <Link
              key={trace.trace_id}
              to={`/traces/${trace.trace_id}`}
              className="block rounded-3xl border border-line bg-panel p-5 shadow-panel"
            >
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-display text-lg font-semibold text-accent">{trace.trace_id}</p>
                  <p className="mt-1 text-sm text-text">{trace.query}</p>
                </div>
                <div className="text-right text-xs text-muted">
                  <p>{t(`route.${trace.route}`)}</p>
                  <p>{trace.updated_at ? formatTime(trace.updated_at) : t("common.na")}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </Panel>
    </AppShell>
  );
}
