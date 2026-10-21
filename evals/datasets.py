"""Labelled evaluation datasets and their loaders.

Datasets are small JSON files under evals/datasets/. Each query/eligibility
case only states the fields it asserts, so scorers never grade a field the
case author didn't label.
"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

from daad_search.api.schemas import SearchFilters
from daad_search.query_understanding.schema import StudentProfile

DATASETS_DIR = Path(__file__).parent / "datasets"

Verdict = Literal["eligible", "likely_eligible", "not_eligible", "unclear"]


class QueryCase(BaseModel):
    id: str
    query: str
    expected_filters: dict
    expected_profile: dict

    @model_validator(mode="after")
    def _known_fields_only(self):
        unknown = (set(self.expected_filters) - set(SearchFilters.model_fields)) | (
            set(self.expected_profile) - set(StudentProfile.model_fields)
        )
        if unknown:
            raise ValueError(f"case {self.id}: unknown expected field(s) {sorted(unknown)}")
        return self


class ProgramSnapshot(BaseModel):
    program_id: int
    course_name: str
    structured_eligibility: dict


class EligibilityCase(BaseModel):
    id: str
    profile: dict
    courses: list[dict] | None
    program_id: int
    expected_verdict: Verdict
    acceptable_verdicts: list[Verdict]
    label_rationale: str

    @model_validator(mode="after")
    def _expected_is_acceptable(self):
        if self.expected_verdict not in self.acceptable_verdicts:
            raise ValueError(f"case {self.id}: expected_verdict must be in acceptable_verdicts")
        return self


class TranscriptCase(BaseModel):
    id: str
    image_path: Path
    courses: list[dict]
    grade_value: float | None


def _check_unique(ids: list[str]) -> None:
    seen: set[str] = set()
    for case_id in ids:
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)


def load_query_cases(path: Path = DATASETS_DIR / "query_cases.json") -> list[QueryCase]:
    cases = [QueryCase(**raw) for raw in json.loads(path.read_text())]
    _check_unique([c.id for c in cases])
    return cases


def load_program_snapshots(path: Path = DATASETS_DIR / "program_snapshots.json") -> dict[int, ProgramSnapshot]:
    return {s.program_id: s for s in (ProgramSnapshot(**raw) for raw in json.loads(path.read_text()))}


def load_eligibility_cases(
    path: Path = DATASETS_DIR / "eligibility_cases.json",
    snapshots: dict[int, ProgramSnapshot] | None = None,
) -> list[EligibilityCase]:
    snapshots = load_program_snapshots() if snapshots is None else snapshots
    cases = [EligibilityCase(**raw) for raw in json.loads(path.read_text())]
    _check_unique([c.id for c in cases])
    for case in cases:
        if case.program_id not in snapshots:
            raise ValueError(f"case {case.id}: no snapshot for program {case.program_id}")
    return cases


def load_transcript_cases(dir: Path = DATASETS_DIR / "transcripts") -> list[TranscriptCase]:
    cases = []
    for truth_path in sorted(dir.glob("*.json")):
        truth = json.loads(truth_path.read_text())
        cases.append(TranscriptCase(
            id=truth_path.stem,
            image_path=truth_path.with_suffix(".png"),
            courses=truth["courses"],
            grade_value=truth.get("grade_value"),
        ))
    return cases
