import { TraceDetail } from "../../features/traces/types";
import { EmptyState } from "../common/EmptyState";
import { Badge } from "../common/Badge";
import { useI18n } from "../../i18n/provider";

function toneForStatus(status: string): "default" | "success" | "warning" | "danger" | "accent" {
  if (status === "completed") return "success";
  if (status === "running") return "accent";
  if (status === "failed") return "danger";
  if (status === "fallback") return "warning";
  return "default";
}

export function TaskPlanPanel({ trace }: { trace: TraceDetail | null }) {
  const { t } = useI18n();

  if (!trace) {
    return <EmptyState title={t("empty.noTaskPlan")} body={t("empty.noTaskPlanBody")} />;
  }

  return (
    <div className="space-y-3">
      {trace.step_results.map((step) => (
        <div key={step.step_id} className="rounded-2xl border border-line bg-white p-4 text-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-text">{t(`task.${step.role}`)}</p>
              <p className="text-xs uppercase tracking-[0.14em] text-muted">{step.step_id}</p>
            </div>
            <Badge tone={toneForStatus(step.status)}>{t(`task.${step.status}`)}</Badge>
          </div>
          <p className="mt-3 text-text">{step.instruction}</p>
          {step.error_message ? <p className="mt-2 text-danger">{step.error_message}</p> : null}
        </div>
      ))}
    </div>
  );
}
