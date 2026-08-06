# src/daad_search/query_understanding/reasoner.py
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

Grades: the program's grade threshold is stated on the German scale, where LOWER numbers are BETTER (1.0 = best possible, 5.0 = fail) -- this is the OPPOSITE direction from a US-style GPA, where HIGHER numbers are better.{grade_conversion_note} If no pre-computed conversion was given above, convert the student's grade to the German scale yourself: for a 4.0-scale US GPA, use the modified Bavarian formula (DAAD's standard convention): German grade = 1 + 3 x (4.0 - GPA) / (4.0 - 1.0). For a percentage-based scale, treat 90%+ as roughly German 1.0-1.5, 80-89% as roughly 1.5-2.0, 70-79% as roughly 2.0-2.5, 60-69% as roughly 2.5-3.0, and below 60% as 3.0 or worse. Sanity-check your converted grade: a WEAK original grade must convert to a WORSE (higher) German number, and a STRONG original grade must convert to a BETTER (lower) German number. Then compare the (given or converted) grade against the program's threshold and briefly note your reasoning and the value used.

Standardized tests: a program's GRE/GMAT requirement may be conditional (see eligibility_condition, e.g. "only for non-EU/EEA applicants") or waived under a stated condition (see waiver, e.g. "waived if CGPA better than 1.3"). Apply these conditions using the student's nationality/grade where relevant.

Language requirements: a program's language requirement lists ACCEPTED TESTS as alternatives -- the student only needs to plausibly meet ONE, not all.

Student profile:
{student_profile}

Candidate programs:
{candidates}

Return one verdict per candidate program_id. Every reasoning string should be 1-3 sentences citing the specific criteria that drove the verdict.
"""

GRADE_CONVERSION_NOTE_TEMPLATE = (
    " The student's grade has already been converted to the German scale using the "
    "modified Bavarian formula: {converted_grade} (1.0 best, 5.0 worst). Use this "
    "pre-computed value directly when comparing against each program's grade "
    "requirement -- do not recompute it yourself."
)


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
    profile_text = profile.model_dump_json(indent=2)
    candidates_text = "\n\n".join(
        f"Program {c.program_id} ({c.course_name}):\n{c.structured_eligibility}"
        for c in candidates
    )
    grade_conversion_note = ""
    if profile.grade_value is not None:
        converted_grade = convert_to_german_scale(profile.grade_value, profile.grade_scale)
        if converted_grade is not None:
            grade_conversion_note = GRADE_CONVERSION_NOTE_TEMPLATE.format(converted_grade=converted_grade)
    return REASONING_PROMPT_TEMPLATE.format(
        student_profile=profile_text,
        candidates=candidates_text,
        grade_conversion_note=grade_conversion_note,
    )


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
