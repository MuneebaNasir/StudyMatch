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

Grades: the program's grade threshold is stated on the German scale, where LOWER numbers are BETTER (1.0 = best possible, 5.0 = fail) -- this is the OPPOSITE direction from a US-style GPA, where HIGHER numbers are better. Before comparing, convert the student's grade to the German scale:
- For a 4.0-scale US GPA, use the modified Bavarian formula (DAAD's standard convention): German grade = 1 + 3 x (4.0 - GPA) / (4.0 - 1.0). Example: a 2.0/4.0 GPA (a weak, below-average performance) converts to approximately German 3.0 -- NOT a good grade, since German grades near 3.0 are only "satisfactory". A 3.9/4.0 GPA (excellent) converts to approximately German 1.1 -- an excellent grade.
- For a percentage-based scale, treat 90%+ as roughly German 1.0-1.5, 80-89% as roughly 1.5-2.0, 70-79% as roughly 2.0-2.5, 60-69% as roughly 2.5-3.0, and below 60% as 3.0 or worse -- adjust for context (country-specific grading norms vary).
- Sanity-check your converted grade: a WEAK original grade (bottom of its scale) must convert to a WORSE (higher) German number, and a STRONG original grade (top of its scale) must convert to a BETTER (lower) German number. If your conversion doesn't follow this direction, redo it.
Then compare the converted grade against the program's threshold and briefly note your reasoning and the converted value.

Standardized tests: a program's GRE/GMAT requirement may be conditional (see eligibility_condition, e.g. "only for non-EU/EEA applicants") or waived under a stated condition (see waiver, e.g. "waived if CGPA better than 1.3"). Apply these conditions using the student's nationality/grade where relevant.

Language requirements: a program's language requirement lists ACCEPTED TESTS as alternatives -- the student only needs to plausibly meet ONE, not all.

Student profile:
{student_profile}

Candidate programs:
{candidates}

Return one verdict per candidate program_id. Every reasoning string should be 1-3 sentences citing the specific criteria that drove the verdict.
"""


def build_reasoning_prompt(profile: StudentProfile, candidates: list[CandidateForReasoning]) -> str:
    profile_text = profile.model_dump_json(indent=2)
    candidates_text = "\n\n".join(
        f"Program {c.program_id} ({c.course_name}):\n{c.structured_eligibility}"
        for c in candidates
    )
    return REASONING_PROMPT_TEMPLATE.format(student_profile=profile_text, candidates=candidates_text)


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
