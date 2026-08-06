import { describe, expect, it } from "vitest";

import type { QueryResult, SearchResult } from "../types";
import { buildVerdictMap, mergeVerdicts } from "./mergeVerdicts";

const BASE_RESULT: SearchResult = {
  id: 1, course_name: "Robotics MSc", university: "TU X", city: null, languages: ["English"],
  subject: null, tuition_fees_text: null, application_deadline_text: null, link: "https://example.com", score: null,
};

describe("buildVerdictMap / mergeVerdicts", () => {
  it("preserves the verdict for a program present in the original query results", () => {
    const original: QueryResult[] = [
      { ...BASE_RESULT, eligibility_verdict: "eligible", eligibility_reasoning: "meets all criteria" },
    ];
    const map = buildVerdictMap(original);

    const merged = mergeVerdicts([BASE_RESULT], map);

    expect(merged[0].eligibility_verdict).toBe("eligible");
    expect(merged[0].eligibility_reasoning).toBe("meets all criteria");
  });

  it("falls back to no_data for a program absent from the verdict map", () => {
    const map = buildVerdictMap([]);
    const merged = mergeVerdicts([{ ...BASE_RESULT, id: 99 }], map);

    expect(merged[0].eligibility_verdict).toBe("no_data");
    expect(merged[0].eligibility_reasoning).toBeNull();
  });
});
