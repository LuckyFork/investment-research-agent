export type EvidenceItem = {
  document_id: string;
  page_num: number | null;
  section_title: string;
  score: number;
  final_score: number;
  chunk_index: number;
  snippet: string;
};

export type TraceSummary = {
  trace_id: string;
  session_id: string;
  query: string;
  complexity: string;
  route: string;
  step_count: number;
  completed_steps: string[];
  failed_steps: string[];
  fallback_triggered: boolean;
  fallback_reason: string;
  compliance_passed: boolean | null;
  final_answer_preview: string;
  artifact_path: string;
  updated_at?: number;
};

export type TaskStep = {
  step_id: string;
  role: string;
  instruction: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown> & {
    evidences?: EvidenceItem[];
    result_count?: number;
    top_score?: number | null;
    result_preview?: string;
  };
  error_message: string;
};

export type TraceDetail = {
  trace_id: string;
  session_id: string;
  query: string;
  rule_analysis: Record<string, unknown>;
  refined_analysis: Record<string, unknown>;
  task_plan: {
    query: string;
    query_analysis: Record<string, unknown>;
    execution_mode: string;
    steps: TaskStep[];
    fallback_strategy: string;
  };
  step_results: TaskStep[];
  final_answer: string;
  compliance_result: Record<string, unknown>;
  fallback_triggered: boolean;
  fallback_reason: string;
  artifact_path: string;
};
