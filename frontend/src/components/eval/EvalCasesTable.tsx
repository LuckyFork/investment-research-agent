import { EvalCaseResult } from "../../features/evals/types";
import { formatPercent } from "../../lib/format";
import { EmptyState } from "../common/EmptyState";
import { useI18n } from "../../i18n/provider";

export function EvalCasesTable({ cases }: { cases: EvalCaseResult[] | undefined }) {
  const { t } = useI18n();

  if (!cases?.length) {
    return <EmptyState title={t("eval.noDetails")} body={t("eval.noDetailsBody")} />;
  }

  const formatBoolean = (value: boolean | null | undefined) => {
    if (value == null) return t("common.na");
    return value ? t("common.yes") : t("common.no");
  };

  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-white">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-canvas/80 text-xs uppercase tracking-[0.14em] text-muted">
          <tr>
            <th className="px-4 py-3">{t("eval.table.case")}</th>
            <th className="px-4 py-3">{t("eval.table.route")}</th>
            <th className="px-4 py-3">{t("eval.table.doc")}</th>
            <th className="px-4 py-3">{t("eval.table.page")}</th>
            <th className="px-4 py-3">{t("eval.table.keywords")}</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((item) => (
            <tr key={item.case_id} className="border-t border-line">
              <td className="px-4 py-3">
                <p className="font-semibold text-text">{item.case_id}</p>
                <p className="text-muted">{item.query}</p>
              </td>
              <td className="px-4 py-3">{formatBoolean(item.route_correct)}</td>
              <td className="px-4 py-3">{formatBoolean(item.document_hit)}</td>
              <td className="px-4 py-3">{formatBoolean(item.page_hit)}</td>
              <td className="px-4 py-3">{formatPercent(item.keyword_hit_ratio)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
