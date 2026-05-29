export type ChatStreamEvent =
  | { type: "text"; content: string; session_id?: string }
  | { type: "tool_start"; tool_name: string; content: string }
  | {
      type: "tool_done";
      tool_name: string;
      content: string;
      payload?: {
        query?: string;
        result_count?: number;
        top_score?: number | null;
        top_evidence?: Record<string, unknown>;
      };
    }
  | { type: "compliance"; compliance_passed: boolean; compliance_issues: Array<Record<string, unknown>> }
  | { type: "done"; session_id: string }
  | { type: "error"; content: string };

export type ChatMessageView = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
};

export type ToolEventView = {
  id: string;
  type: "tool_start" | "tool_done";
  toolName: string;
  content: string;
  payload?: {
    query?: string;
    result_count?: number;
    top_score?: number | null;
    top_evidence?: Record<string, unknown>;
  };
};
