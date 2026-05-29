export type EvalSummary = {
  total_cases: number;
  route_accuracy: number;
  document_hit_rate: number;
  page_hit_rate: number;
  keyword_hit_rate: number;
  compliance_accuracy: number;
};

export type EvalCaseResult = {
  case_id: string;
  query: string;
  actual_complexity?: string | null;
  actual_route?: string | null;
  route_correct?: boolean | null;
  document_hit?: boolean | null;
  page_hit?: boolean | null;
  keyword_hit_ratio: number;
  compliance_correct?: boolean | null;
  compliance_passed?: boolean | null;
  trace_path: string;
  answer_preview: string;
  notes: string[];
};
