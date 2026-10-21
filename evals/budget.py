"""Upfront LLM-call estimate, printed before an eval run spends any quota."""

PROVIDERS = ("groq", "mistral", "gemini")


def estimate_calls(
    suites: list[str],
    counts: dict[str, int],
    judge: bool,
    per_provider: bool,
    gemini_cap: int,
    per_provider_cases: int = 3,
    include_transcript_in_per_provider: bool = False,
) -> dict[str, int]:
    """Model invocations the run will make, assuming no provider fails.

    `gemini_max` is the worst case for Gemini: every transcript case (Gemini is
    the first vision provider) plus every text case that falls through to it,
    bounded by the quota guard's cap.
    """
    if per_provider:
        per_provider_suites = [
            s for s in suites if s != "transcript" or include_transcript_in_per_provider
        ]
        total = sum(min(per_provider_cases, counts[s]) for s in per_provider_suites) * len(PROVIDERS)
        if judge and "eligibility" in per_provider_suites:
            total += min(per_provider_cases, counts["eligibility"]) * len(PROVIDERS)
        gemini_worst = sum(min(per_provider_cases, counts[s]) for s in per_provider_suites)
    else:
        total = sum(counts[s] for s in suites)
        if judge and "eligibility" in suites:
            total += counts["eligibility"]
        gemini_worst = sum(counts[s] for s in suites)
    return {"total": total, "gemini_max": min(gemini_cap, gemini_worst)}
