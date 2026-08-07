import type { EligibilityVerdictValue } from "../types";

export const VERDICT_STYLES: Record<EligibilityVerdictValue, string> = {
  eligible: "bg-green-100 text-green-800",
  likely_eligible: "bg-orange-100 text-orange-800",
  not_eligible: "bg-red-100 text-red-800",
  unclear: "bg-amber-100 text-amber-800",
  no_data: "bg-stone-100 text-stone-600",
};

export const VERDICT_LABELS: Record<EligibilityVerdictValue, string> = {
  eligible: "Eligible",
  likely_eligible: "Likely eligible",
  not_eligible: "Not eligible",
  unclear: "Unclear",
  no_data: "Not evaluated",
};
