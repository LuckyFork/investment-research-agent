import { useMemo, useState } from "react";
import { Bot, FileSearch, ShieldCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { AppShell } from "../components/layout/AppShell";
import { Panel } from "../components/layout/Panel";
import { ChatComposer } from "../components/chat/ChatComposer";
import { MessageList } from "../components/chat/MessageList";
import { StreamStatus } from "../components/chat/StreamStatus";
import { QueryAnalysisCard } from "../components/execution/QueryAnalysisCard";
import { ToolEventTimeline } from "../components/execution/ToolEventTimeline";
import { TaskPlanPanel } from "../components/execution/TaskPlanPanel";
import { EvidencePanel } from "../components/evidence/EvidencePanel";
import { TraceSummaryCard } from "../components/evidence/TraceSummaryCard";
import { streamChat } from "../features/chat/api";
import type { ChatMessageView, ChatStreamEvent, ToolEventView } from "../features/chat/types";
import { fetchTraceDetail, fetchLatestTrace } from "../features/traces/api";
import type { TraceDetail, TraceSummary } from "../features/traces/types";
import { DEFAULT_SESSION_ID } from "../lib/constants";
import { useI18n } from "../i18n/provider";

function requestId() {
  return `web-${Date.now()}`;
}

export function ConsolePage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState(DEFAULT_SESSION_ID);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [toolEvents, setToolEvents] = useState<ToolEventView[]>([]);
  const [compliancePassed, setCompliancePassed] = useState<boolean | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [traceSummary, setTraceSummary] = useState<TraceSummary | null>(null);
  const [traceDetail, setTraceDetail] = useState<TraceDetail | null>(null);

  const queryAnalysis = useMemo(
    () => (traceDetail?.refined_analysis as Record<string, unknown> | null) ?? null,
    [traceDetail]
  );

  async function refreshTrace(currentSessionId: string) {
    const latest = await fetchLatestTrace(currentSessionId);
    setTraceSummary(latest);
    if (latest?.trace_id) {
      const detail = await fetchTraceDetail(latest.trace_id);
      setTraceDetail(detail);
      queryClient.invalidateQueries({ queryKey: ["traces"] });
    }
  }

  async function handleSubmit() {
    if (!input.trim() || streaming) return;

    const currentInput = input.trim();
    const currentRequestId = requestId();
    setStreaming(true);
    setError("");
    setToolEvents([]);
    setCompliancePassed(null);
    setTraceSummary(null);
    setTraceDetail(null);

    const userMessage: ChatMessageView = {
      id: `${currentRequestId}-user`,
      role: "user",
      content: currentInput
    };
    const assistantMessageId = `${currentRequestId}-assistant`;

    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantMessageId, role: "assistant", content: "" }
    ]);
    setInput("");

    try {
      await streamChat(
        {
          sessionId,
          message: currentInput,
          requestId: currentRequestId
        },
        async (event: ChatStreamEvent) => {
          if (event.type === "text") {
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${event.content}` }
                  : message
              )
            );
          }

          if (event.type === "tool_start" || event.type === "tool_done") {
            setToolEvents((prev) => [
              ...prev,
              {
                id: `${currentRequestId}-${prev.length + 1}`,
                type: event.type,
                toolName: event.tool_name,
                content: event.content,
                payload: event.type === "tool_done" ? event.payload : undefined
              }
            ]);
          }

          if (event.type === "compliance") {
            setCompliancePassed(event.compliance_passed);
          }

          if (event.type === "error") {
            setError(event.content);
          }

          if (event.type === "done") {
            await refreshTrace(sessionId);
            setStreaming(false);
          }
        },
        (streamError) => {
          setStreaming(false);
          setError(streamError.message);
        }
      );
    } catch (streamError) {
      setStreaming(false);
      setError((streamError as Error).message);
    }
  }

  return (
    <AppShell>
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.95fr_0.9fr]">
        <div className="space-y-6">
          <Panel title={t("console.conversation")}>
            <div className="mb-5 flex items-center gap-3 text-sm text-muted">
              <Bot className="h-4 w-4" />
              {t("console.conversationHint")}
            </div>
            <ChatComposer
              sessionId={sessionId}
              input={input}
              streaming={streaming}
              onSessionChange={setSessionId}
              onInputChange={setInput}
              onSubmit={handleSubmit}
            />
            <div className="mt-5">
              <StreamStatus streaming={streaming} error={error} />
            </div>
            <div className="mt-5 max-h-[540px] space-y-3 overflow-auto pr-1">
              <MessageList messages={messages} />
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title={t("console.queryAnalysis")}>
            <QueryAnalysisCard analysis={queryAnalysis} />
          </Panel>
          <Panel title={t("console.toolTimeline")}>
            <div className="mb-3 flex items-center gap-3 text-sm text-muted">
              <FileSearch className="h-4 w-4" />
              {t("console.toolTimelineHint")}
            </div>
            <ToolEventTimeline events={toolEvents} />
          </Panel>
          <Panel title={t("console.taskPlan")}>
            <TaskPlanPanel trace={traceDetail} />
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title={t("console.traceSummary")}>
            <TraceSummaryCard trace={traceSummary} />
          </Panel>
          <Panel title={t("console.evidence")}>
            <EvidencePanel trace={traceDetail} />
          </Panel>
          <Panel title={t("console.compliance")}>
            <div className="flex items-center gap-3 text-sm">
              <ShieldCheck className="h-4 w-4 text-accent" />
              <span className="text-muted">{t("console.currentStatus")}</span>
            </div>
            <p className="mt-3 text-lg font-semibold text-text">
              {compliancePassed == null
                ? t("console.noCompliance")
                : compliancePassed
                  ? t("console.passed")
                  : t("console.blocked")}
            </p>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
