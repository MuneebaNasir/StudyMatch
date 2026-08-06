from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    languages: list[str] | None = None
    max_tuition_free_only: bool | None = None
    subject: str | None = None
    city: str | None = None
    course_type: int | None = None


class SearchRequest(BaseModel):
    filters: SearchFilters | None = None
    semantic_query: str | None = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SearchResult(BaseModel):
    id: int
    course_name: str
    university: str
    city: str | None
    languages: list[str]
    subject: str | None
    tuition_fees_text: str | None
    application_deadline_text: str | None
    link: str
    score: float | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_matched: int


class ProgramDetail(SearchResult):
    course_type: int
    degree: str | None
    duration: str | None
    beginning: str | None
    raw_sections: dict
    structured_eligibility: dict | None = None
