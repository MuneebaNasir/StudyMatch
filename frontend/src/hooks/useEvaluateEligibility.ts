import { useMutation } from "@tanstack/react-query";

import { postEvaluateEligibility } from "../api/client";
import type { StudentProfile } from "../types";

export function useEvaluateEligibility() {
  return useMutation({
    mutationFn: ({ programId, profile }: { programId: number; profile: StudentProfile }) =>
      postEvaluateEligibility(programId, profile),
  });
}
