from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DAAD_HOST = "https://www2.daad.de"


@dataclass
class ProgramSummary:
    id: int
    course_name: str
    course_name_short: Optional[str]
    university: str
    city: Optional[str]
    languages: list[str]
    subject: Optional[str]
    course_type: int
    duration: Optional[str]
    beginning: Optional[str]
    tuition_fees_text: Optional[str]
    has_tuition_fees: bool
    link: str


def _has_fees(tuition_text: Optional[str]) -> bool:
    if not tuition_text:
        return True
    return "no tuition fees" not in tuition_text.lower()


def _absolute_link(link: str) -> str:
    if link.startswith("http"):
        return link
    return DAAD_HOST + link


def parse_program_summary(raw: dict) -> ProgramSummary:
    return ProgramSummary(
        id=raw["id"],
        course_name=raw["courseName"],
        course_name_short=raw.get("courseNameShort"),
        university=raw.get("academy", ""),
        city=raw.get("city"),
        languages=raw.get("languages") or [],
        subject=raw.get("subject"),
        course_type=raw["courseType"],
        duration=raw.get("programmeDuration"),
        beginning=raw.get("beginning"),
        tuition_fees_text=raw.get("tuitionFees"),
        has_tuition_fees=_has_fees(raw.get("tuitionFees")),
        link=_absolute_link(raw["link"]),
    )


def parse_search_response(payload: dict) -> list[ProgramSummary]:
    return [parse_program_summary(course) for course in payload.get("courses", [])]
