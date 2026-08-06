from typing import Literal

from pydantic import BaseModel, Field

from ..api.schemas import SearchFilters, SearchResult


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


class QueryRequest(BaseModel):
    query: str
    limit: int = Field(20, ge=1, le=100)


class QueryResult(SearchResult):
    eligibility_verdict: Literal["eligible", "likely_eligible", "not_eligible", "unclear", "no_data"]
    eligibility_reasoning: str | None = None


class QueryResponse(BaseModel):
    results: list[QueryResult]
    total_matched: int
    extracted_filters: SearchFilters | None = None
    extracted_profile: StudentProfile | None = None
    semantic_query: str | None = None
