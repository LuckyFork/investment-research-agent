import { EvidenceCard } from "./EvidenceCard";
import { TraceDetail } from "../../features/traces/types";
import { EmptyState } from "../common/EmptyState";
import { useI18n } from "../../i18n/provider";

export function EvidencePanel({ trace }: { trace: TraceDetail | null }) {
  const { t } = useI18n();

  if (!trace) {
    return <EmptyState title={t("empty.noEvidence")} body={t("empty.noEvidenceBody")} />;
  }

  const evidenceSteps = trace.step_results.filter((step) => step.role === "retriever");

  if (!evidenceSteps.length) {
    return <EmptyState title={t("empty.noRetrievalSteps")} body={t("empty.noRetrievalStepsBody")} />;
  }

  return (
    <div className="space-y-3">
      {evidenceSteps.map((step) => (
        <div key={step.step_id} className="rounded-2xl border border-line bg-white p-4 text-sm">
          <p className="font-semibold text-text">{String(step.input_payload.query ?? step.step_id)}</p>
          {Array.isArray(step.output_payload.evidences) && step.output_payload.evidences.length ? (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>
                  {t("evidence.hitCount", {
                    count: step.output_payload.result_count ?? step.output_payload.evidences.length
                  })}
                </span>
                {typeof step.output_payload.top_score === "number" ? (
                  <span>{t("evidence.topScore", { score: step.output_payload.top_score.toFixed(4) })}</span>
                ) : null}
              </div>
              {step.output_payload.evidences.map((evidence, index) => (
                <EvidenceCard
                  key={`${step.step_id}-${evidence.document_id}-${evidence.chunk_index}-${index}`}
                  evidence={evidence}
                  index={index + 1}
                  query={String(step.input_payload.query ?? "")}
                />
              ))}
            </div>
          ) : (
            <pre className="mt-3 whitespace-pre-wrap font-body text-sm text-text">
              {String(step.output_payload.result_preview ?? t("evidence.noPreview"))}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
