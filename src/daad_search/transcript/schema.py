from typing import Literal

from pydantic import BaseModel


class ExtractedCourse(BaseModel):
    name: str
    grade: str | None = None


class TranscriptExtraction(BaseModel):
    courses: list[ExtractedCourse] = []
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    degree_field: str | None = None
    extraction_confidence: Literal["high", "medium", "low"]


class TranscriptUploadResponse(BaseModel):
    session_token: str
    courses: list[ExtractedCourse]
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    degree_field: str | None = None
    extraction_confidence: Literal["high", "medium", "low"]
