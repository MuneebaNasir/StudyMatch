import type { EligibilityVerdictValue, QueryResult, SearchResult } from "../types";

export interface VerdictInfo {
  verdict: EligibilityVerdictValue;
  reasoning: string | null;
}

export function buildVerdictMap(results: QueryResult[]): Map<number, VerdictInfo> {
  return new Map(results.map((r) => [r.id, { verdict: r.eligibility_verdict, reasoning: r.eligibility_reasoning }]));
}

export function mergeVerdicts(results: SearchResult[], verdictMap: Map<number, VerdictInfo>): QueryResult[] {
  return results.map((r) => {
    const info = verdictMap.get(r.id);
    return {
      ...r,
      eligibility_verdict: info?.verdict ?? "no_data",
      eligibility_reasoning: info?.reasoning ?? null,
    };
  });
}
