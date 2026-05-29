import { httpGet } from "../../lib/http";
import type { TraceDetail, TraceSummary } from "./types";

type ApiResponse<T> = { success: boolean; data: T };

export async function fetchTraceList() {
  const response = await httpGet<ApiResponse<TraceSummary[]>>("/api/v1/traces");
  return response.data;
}

export async function fetchTraceSummary(traceId: string) {
  const response = await httpGet<ApiResponse<TraceSummary>>(`/api/v1/traces/${traceId}/summary`);
  return response.data;
}

export async function fetchTraceDetail(traceId: string) {
  const response = await httpGet<ApiResponse<TraceDetail>>(`/api/v1/traces/${traceId}`);
  return response.data;
}

export async function fetchLatestTrace(sessionId: string) {
  const response = await httpGet<ApiResponse<TraceSummary | null>>(`/api/v1/traces/sessions/${sessionId}/latest`);
  return response.data;
}
