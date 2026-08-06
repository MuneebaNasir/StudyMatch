# src/daad_search/query_understanding/reasoner.py
import json
import logging

from .llm import get_fallback_llm
from .schema import BatchEligibilityReasoning, CandidateForReasoning, EligibilityVerdict, StudentProfile

logger = logging.getLogger(__name__)

REASONING_PROMPT_TEMPLATE = """You are assessing whether a prospective student is eligible for German university master's programs, based on each program's structured eligibility criteria and the student's stated profile.

For EACH candidate program below, decide a verdict:
- "eligible": the student clearly meets all stated requirements
- "likely_eligible": the student appears to meet requirements, but some ambiguity or missing information remains
- "not_eligible": the student clearly fails to meet at least one stated requirement
- "unclear": there isn't enough information in either the program's criteria or the student's profile to judge

Grades: the program's grade threshold is stated on the German scale, where LOWER numbers are BETTER (1.0 = best possible, 5.0 = fail). If the student profile below includes a "grade_value_on_german_scale" field, that is the ALREADY-CONVERTED value on the German scale -- use it directly and do not recompute anything from "grade_value"/"grade_scale". If that field is absent, convert the student's grade to the German scale yourself: for a 4.0-scale US GPA, use the modified Bavarian formula (DAAD's standard convention): German grade = 1 + 3 x (4.0 - GPA) / (4.0 - 1.0). For a percentage-based scale, treat 90%+ as roughly German 1.0-1.5, 80-89% as roughly 1.5-2.0, 70-79% as roughly 2.0-2.5, 60-69% as roughly 2.5-3.0, and below 60% as 3.0 or worse. Then compare the grade against the program's threshold and briefly note your reasoning and the value used.

Standardized tests: a program's GRE/GMAT requirement may be conditional (see eligibility_condition, e.g. "only for non-EU/EEA applicants") or waived under a stated condition (see waiver, e.g. "waived if CGPA better than 1.3"). Apply these conditions using the student's nationality/grade where relevant.

Language requirements: a program's language requirement lists ACCEPTED TESTS as alternatives -- the student only needs to plausibly meet ONE, not all.

Student profile:
{student_profile}

Candidate programs:
{candidates}

Return one verdict per candidate program_id. Every reasoning string should be 1-3 sentences citing the specific criteria that drove the verdict.
"""


def convert_to_german_scale(grade_value: float, grade_scale: str | None) -> float | None:
    """Deterministically convert a well-known grading scale to the German scale
    (1.0 best, 5.0 worst) using DAAD's modified Bavarian formula. Returns None
    for scales this doesn't recognize -- the prompt falls back to asking the
    LLM to reason about the conversion itself in that case."""
    if grade_scale is None:
        return None
    scale_text = grade_scale.lower()

    if "4.0" in scale_text or "gpa" in scale_text:
        converted = 1 + 3 * (4.0 - grade_value) / (4.0 - 1.0)
    elif "%" in scale_text or "percent" in scale_text or "100" in scale_text:
        converted = 1 + 3 * (100.0 - grade_value) / (100.0 - 50.0)
    else:
        return None

    return round(max(1.0, min(5.0, converted)), 2)


def build_reasoning_prompt(profile: StudentProfile, candidates: list[CandidateForReasoning]) -> str:
    profile_dict = profile.model_dump()
    if profile.grade_value is not None:
        converted = convert_to_german_scale(profile.grade_value, profile.grade_scale)
        if converted is not None:
            profile_dict["grade_value_on_german_scale"] = converted
    profile_text = json.dumps(profile_dict, indent=2)

    candidates_text = "\n\n".join(
        f"Program {c.program_id} ({c.course_name}):\n{c.structured_eligibility}"
        for c in candidates
    )
    return REASONING_PROMPT_TEMPLATE.format(
        student_profile=profile_text, candidates=candidates_text
    )


# KNOWN LIMITATION -- grade comparison against the German scale (1.0 best,
# 5.0 worst) has been observed to be unreliable on weaker fallback-tier
# models. The numeric conversion itself is now deterministic (see
# convert_to_german_scale, injected into the prompt as
# grade_value_on_german_scale) and has been verified correct and correctly
# retrieved by the LLM -- the remaining failure mode is the model getting
# the actual "is 3.0 better or worse than the 2.5 threshold, given lower is
# better" comparison backwards, despite the direction being stated
# explicitly. Observed reproducibly via Mistral (the fallback chain's
# secondary tier); not yet re-verified against Groq's primary-tier model,
# which was inaccessible (403, account-side) throughout this task's
# development. Re-test once Groq access is restored -- if verdicts are
# reliable there, this may be specific to weaker fallback tiers rather than
# a fundamental prompt limitation.
def reason_about_eligibility(
    profile: StudentProfile, candidates: list[CandidateForReasoning]
) -> list[EligibilityVerdict] | None:
    if not candidates:
        return []
    prompt = build_reasoning_prompt(profile, candidates)
    try:
        result: BatchEligibilityReasoning = get_fallback_llm(BatchEligibilityReasoning).invoke(prompt)
        return result.verdicts
    except Exception:
        logger.exception("Failed to reason about eligibility for %d candidates", len(candidates))
        return None
