from typing import Literal

from pydantic import BaseModel

from ..api.schemas import SearchFilters


class StudentProfile(BaseModel):
    degree_field: str | None = None
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    other_notes: str | None = None


class ParsedQuery(BaseModel):
    filters: SearchFilters
    semantic_query: str | None = None
    student_profile: StudentProfile


class EligibilityVerdict(BaseModel):
    program_id: int
    verdict: Literal["eligible", "likely_eligible", "not_eligible", "unclear"]
    reasoning: str


class BatchEligibilityReasoning(BaseModel):
    verdicts: list[EligibilityVerdict] = []


class CandidateForReasoning(BaseModel):
    program_id: int
    course_name: str
    structured_eligibility: dict
