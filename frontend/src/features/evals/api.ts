import { httpGet } from "../../lib/http";
import type { EvalCaseResult, EvalSummary } from "./types";

type ApiResponse<T> = { success: boolean; data: T };

export async function fetchEvalSummary() {
  const response = await httpGet<ApiResponse<EvalSummary>>("/api/v1/evals/latest-summary");
  return response.data;
}

export async function fetchEvalDetails() {
  const response = await httpGet<ApiResponse<EvalCaseResult[]>>("/api/v1/evals/latest-details");
  return response.data;
}
