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

Grades: the program's grade threshold is stated on the German scale (1.0 best, 5.0 worst, typically ~4.0 or better required). The student's grade may be stated on a different scale (e.g. a 4.0 GPA scale, or a percentage) -- convert and compare using your own knowledge of standard grade-scale equivalences (similar to DAAD's own conventions), and briefly note your reasoning.

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
