from typing import Literal

from pydantic import BaseModel, Field


class ExtractedCourse(BaseModel):
    name: str
    grade: str | None = None


class TranscriptExtraction(BaseModel):
    courses: list[ExtractedCourse] = []
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    degree_field: str | None = None
    extraction_confidence: Literal["high", "medium", "low"] = "medium"


class TranscriptUploadResponse(BaseModel):
    courses: list[ExtractedCourse]
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    degree_field: str | None = None
    extraction_confidence: Literal["high", "medium", "low"]


class TranscriptCourseInput(BaseModel):
    name: str = Field(max_length=300)
    grade: str | None = Field(None, max_length=50)


class TranscriptContext(BaseModel):
    """Transcript data the client sends back with each /query.

    The server never stores transcript extractions -- the browser holds them
    in memory and resends them, so nothing personal outlives the request.
    The bounds keep a hand-crafted request from bloating the reasoning
    prompt, since this is client-controlled input.
    """

    courses: list[TranscriptCourseInput] = Field(default_factory=list, max_length=200)
    grade_value: float | None = None
    grade_scale: str | None = Field(None, max_length=50)
    nationality: str | None = Field(None, max_length=100)
    degree_field: str | None = Field(None, max_length=200)
