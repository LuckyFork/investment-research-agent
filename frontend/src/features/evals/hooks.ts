import { useQuery } from "@tanstack/react-query";

import { fetchEvalDetails, fetchEvalSummary } from "./api";

export function useEvalSummary() {
  return useQuery({
    queryKey: ["eval-summary"],
    queryFn: fetchEvalSummary
  });
}

export function useEvalDetails() {
  return useQuery({
    queryKey: ["eval-details"],
    queryFn: fetchEvalDetails
  });
}
