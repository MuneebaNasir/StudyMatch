from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SearchFilters(BaseModel):
    languages: Optional[list[str]] = None
    max_tuition_free_only: Optional[bool] = None
    subject: Optional[str] = None
    city: Optional[str] = None
    course_type: Optional[int] = None


class SearchRequest(BaseModel):
    filters: Optional[SearchFilters] = None
    semantic_query: Optional[str] = None
    limit: int = 20


class SearchResult(BaseModel):
    id: int
    course_name: str
    university: str
    city: Optional[str]
    languages: list[str]
    subject: Optional[str]
    tuition_fees_text: Optional[str]
    application_deadline_text: Optional[str]
    link: str
    score: Optional[float] = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_matched: int


class ProgramDetail(SearchResult):
    course_type: int
    degree: Optional[str]
    duration: Optional[str]
    beginning: Optional[str]
    raw_sections: dict
