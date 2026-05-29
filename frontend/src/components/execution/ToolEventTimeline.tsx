import { ToolEventView } from "../../features/chat/types";
import { EmptyState } from "../common/EmptyState";
import { Badge } from "../common/Badge";
import { useI18n } from "../../i18n/provider";

function formatToolSummary(event: ToolEventView, t: (key: string, vars?: Record<string, string | number>) => string) {
  if (event.type === "tool_start") {
    return event.content;
  }

  if (event.payload) {
    const parts: string[] = [];
    if (typeof event.payload.result_count === "number") {
      parts.push(t("tool.hitCount", { count: event.payload.result_count }));
    }
    if (typeof event.payload.top_score === "number") {
      parts.push(t("tool.topScore", { score: event.payload.top_score.toFixed(4) }));
    }
    if (event.payload.top_evidence?.document_id) {
      const page = String(event.payload.top_evidence.page_num ?? "?");
      const section = String(event.payload.top_evidence.section_title ?? "").trim();
      parts.push(
        `${String(event.payload.top_evidence.document_id)} / ${t("tool.page", { page })}${section ? ` / ${section}` : ""}`
      );
    }
    if (parts.length) {
      return parts.join(" · ");
    }
  }

  return event.content;
}

export function ToolEventTimeline({ events }: { events: ToolEventView[] }) {
  const { t } = useI18n();

  if (!events.length) {
    return <EmptyState title={t("empty.noToolActivity")} body={t("empty.noToolActivityBody")} />;
  }

  return (
    <div className="space-y-3">
      {events.map((event) => (
        <div key={event.id} className="rounded-2xl border border-line bg-white p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold text-text">{event.toolName}</p>
            <Badge tone={event.type === "tool_start" ? "warning" : "accent"}>
              {event.type === "tool_start" ? t("tool.toolStart") : t("tool.toolDone")}
            </Badge>
          </div>
          {event.payload?.query ? (
            <p className="mt-2 text-xs text-muted">{event.payload.query}</p>
          ) : null}
          <p className="mt-2 text-text">{formatToolSummary(event, t)}</p>
        </div>
      ))}
    </div>
  );
}
