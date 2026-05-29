import { useQuery } from "@tanstack/react-query";

import { fetchLatestTrace, fetchTraceDetail, fetchTraceList } from "./api";

export function useTraceList() {
  return useQuery({
    queryKey: ["traces"],
    queryFn: fetchTraceList
  });
}

export function useTraceDetail(traceId: string) {
  return useQuery({
    queryKey: ["trace", traceId],
    queryFn: () => fetchTraceDetail(traceId),
    enabled: Boolean(traceId)
  });
}

export function useLatestTrace(sessionId: string) {
  return useQuery({
    queryKey: ["latest-trace", sessionId],
    queryFn: () => fetchLatestTrace(sessionId),
    enabled: Boolean(sessionId)
  });
}
