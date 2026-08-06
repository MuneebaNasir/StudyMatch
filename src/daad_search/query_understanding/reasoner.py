# src/daad_search/query_understanding/reasoner.py
import json
import logging
import re

from .llm import get_fallback_llm
from .schema import BatchEligibilityReasoning, CandidateForReasoning, EligibilityVerdict, StudentProfile

logger = logging.getLogger(__name__)

REASONING_PROMPT_TEMPLATE = """You are assessing whether a prospective student is eligible for German university master's programs, based on each program's structured eligibility criteria and the student's stated profile.

For EACH candidate program below, decide a verdict:
- "eligible": the student clearly meets all stated requirements
- "likely_eligible": the student appears to meet requirements, but some ambiguity or missing information remains
- "not_eligible": the student clearly fails to meet at least one stated requirement
- "unclear": there isn't enough information in either the program's criteria or the student's profile to judge

Grades: the program's grade threshold is stated on the German scale, where LOWER numbers are BETTER (1.0 = best possible, 5.0 = fail). If the student profile below includes a "grade_value_on_german_scale" field, that is the ALREADY-CONVERTED value on the German scale -- use it directly and do not recompute anything from "grade_value"/"grade_scale". If that field is absent, convert the student's grade to the German scale yourself: for a 4.0-scale US GPA, use the modified Bavarian formula (DAAD's standard convention): German grade = 1 + 3 x (4.0 - GPA) / (4.0 - 1.0). For a 10-point CGPA scale (common in India and Pakistan, where 10 is best), use the same formula against that scale: German grade = 1 + 3 x (10.0 - CGPA) / (10.0 - 5.0) -- do NOT feed a 10-point CGPA into the 4.0-scale formula. For a percentage-based scale, treat 90%+ as roughly German 1.0-1.5, 80-89% as roughly 1.5-2.0, 70-79% as roughly 2.0-2.5, 60-69% as roughly 2.5-3.0, and below 60% as 3.0 or worse. Then compare the grade against the program's threshold and briefly note your reasoning and the value used.

Standardized tests: a program's GRE/GMAT requirement may be conditional (see eligibility_condition, e.g. "only for non-EU/EEA applicants") or waived under a stated condition (see waiver, e.g. "waived if CGPA better than 1.3"). Apply these conditions using the student's nationality/grade where relevant.

Language requirements: a program's language requirement lists ACCEPTED TESTS as alternatives -- the student only needs to plausibly meet ONE, not all.

Student profile:
{student_profile}

Candidate programs:
{candidates}

Return one verdict per candidate program_id. Every reasoning string should be 1-3 sentences citing the specific criteria that drove the verdict.
"""


# Standalone numbers in a scale description ("4.0 GPA scale (USA)" -> 4.0,
# "10-point CGPA" -> 10, "1000 point scale" -> 1000). Lookarounds keep a
# number whole so "1000" never reads as "100" and "10.0" never as "10" + "0".
_SCALE_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")

# Detected scale -> (best-possible value, the value anchored to German 4.0,
# i.e. the typical minimum passing grade). Both feed the modified Bavarian
# formula: german = 1 + 3 * (best - value) / (best - min_pass).
_SCALE_ANCHORS: dict[str, tuple[float, float]] = {
    "percentage": (100.0, 50.0),
    # India/Pakistan 10-point CGPA: 10 best, 5 the usual pass mark.
    "cgpa_10": (10.0, 5.0),
    # US-style 4.0 GPA: 4.0 best, 1.0 the usual pass mark.
    "gpa_4": (4.0, 1.0),
}


def detect_grade_scale(grade_scale: str | None) -> str | None:
    """Identify which known grading scale a free-text scale description names.

    Returns a key of `_SCALE_ANCHORS`, or None when the description doesn't
    clearly name a scale this module knows how to convert.

    Detection is deliberately order-sensitive: the scale SIZE (10, 4, 100)
    decides, and only a description with no size indicator at all falls back
    to reading a bare "GPA" as the US 4.0 scale. A substring test for "gpa"
    alone would match the "gpa" inside "CGPA", so "10.0 CGPA scale (India)"
    would be converted with the 4.0-scale formula.
    """
    if grade_scale is None:
        return None
    scale_text = grade_scale.lower()

    # Percentages need an explicit percent signal: a bare "100" also appears
    # in "1000 point scale" and in plenty of unrelated text.
    if "%" in scale_text or "percent" in scale_text:
        return "percentage"

    numbers = {float(match) for match in _SCALE_NUMBER_RE.findall(scale_text)}
    if 10.0 in numbers:
        return "cgpa_10"
    if 4.0 in numbers:
        return "gpa_4"
    if numbers:
        # Some other scale size is named (5.0, 20, 1000, ...) -- not one this
        # module has a formula for. Don't guess.
        return None
    # No size named at all: a bare "GPA"/"CGPA" conventionally means 4.0.
    if "gpa" in scale_text:
        return "gpa_4"
    return None


def convert_to_german_scale(grade_value: float, grade_scale: str | None) -> float | None:
    """Deterministically convert a well-known grading scale to the German scale
    (1.0 best, 5.0 worst) using DAAD's modified Bavarian formula. Returns None
    for scales this doesn't recognize, and for a grade that falls outside the
    detected scale's own range -- an out-of-range value is evidence the scale
    was misidentified, so returning None (which makes the prompt fall back to
    asking the LLM to reason about the conversion) is safer than forcing a
    nonsense number into a plausible-looking one."""
    scale = detect_grade_scale(grade_scale)
    if scale is None:
        return None

    best, min_pass = _SCALE_ANCHORS[scale]
    if not 0.0 <= grade_value <= best:
        return None

    converted = 1 + 3 * (best - grade_value) / (best - min_pass)
    # Only values at the very bottom of a correctly-identified scale can land
    # outside 1.0-5.0 now (e.g. 0%), so clamping here is a rounding-edge fix,
    # not a cover-up for a misdetected scale.
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
