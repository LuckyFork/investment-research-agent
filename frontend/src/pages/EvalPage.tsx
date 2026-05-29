import { EvalCasesTable } from "../components/eval/EvalCasesTable";
import { EvalSummaryCards } from "../components/eval/EvalSummaryCards";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { AppShell } from "../components/layout/AppShell";
import { Panel } from "../components/layout/Panel";
import { useEvalDetails, useEvalSummary } from "../features/evals/hooks";
import { useI18n } from "../i18n/provider";

export function EvalPage() {
  const { t } = useI18n();
  const summary = useEvalSummary();
  const details = useEvalDetails();

  return (
    <AppShell>
      <div className="space-y-6">
        <Panel title={t("eval.summary")}>
          {summary.isLoading ? <LoadingState label={t("eval.loadingSummary")} /> : null}
          {summary.error ? <ErrorState message={(summary.error as Error).message} /> : null}
          <EvalSummaryCards summary={summary.data} />
        </Panel>
        <Panel title={t("eval.cases")}>
          {details.isLoading ? <LoadingState label={t("eval.loadingDetails")} /> : null}
          {details.error ? <ErrorState message={(details.error as Error).message} /> : null}
          <EvalCasesTable cases={details.data} />
        </Panel>
      </div>
    </AppShell>
  );
}
