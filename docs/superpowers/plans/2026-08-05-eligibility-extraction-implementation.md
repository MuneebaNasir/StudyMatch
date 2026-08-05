# Eligibility Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable, idempotent, auto-resumable pipeline that reads each program's raw admission text (already in Postgres from the data-foundation spec) and uses an LLM (Groq's `llama-3.3-70b-versatile`, free tier, via LangChain structured output) to produce structured eligibility fields, stored in a new `eligibility` table.

**Architecture:** A new `extraction/` package (schema, extractor, pipeline) parallel to the existing `ingestion/` package. Candidate selection is a `LEFT JOIN` against the new `eligibility` table so re-running the CLI command only ever processes programs still missing extraction. Per-program failure isolation plus a consecutive-failure circuit breaker (quota exhaustion looks identical across many programs in a row — no point burning through the rest of the catalog once detected).

**Tech Stack:** LangChain (`langchain-groq`) for the LLM call and structured output, Groq API (`llama-3.3-70b-versatile`), SQLAlchemy/asyncpg for the new table, Pydantic for the extraction schema.

## Global Constraints

- Python 3.11+, `src/` package layout (`src/daad_search/extraction/...`), native `T | None` union syntax — no `Optional[T]`, no `from __future__ import annotations`. Always verify with `.venv/bin/python --version` (should print `Python 3.11.15`) before running anything — bare `python3` on this machine resolves to system Python 3.9.6, which has broken prior implementers on this project twice.
- The Groq LLM call (via `langchain-groq`) is synchronous — same pattern as `voyageai`/`qdrant-client` elsewhere in this codebase. Any call to it from async code (the pipeline) must go through `asyncio.to_thread(...)`.
- Every claim in `EligibilityExtraction` must carry a verbatim, self-contained `source_quote` — this is validated behavior from live testing during design, not optional polish.
- `standardized_tests` is reserved for GRE/GMAT only. Language proficiency tests (IELTS, TOEFL, TOEIC, Cambridge, PTE, etc.) always go under `LanguageRequirement.accepted_tests`, never `standardized_tests` — this exact separation was validated live against real DAAD text; getting it wrong was the most serious bug caught during design (alternative tests being marked as separately mandatory).
- Candidate selection excludes programs missing an eligibility row AND missing all three of `admission_requirements`/`german_language`/`english_language` in `raw_sections` — never send a program with no relevant text to the LLM.
- Per-program failure isolation: one program's extraction failure must never abort the run. A 5-consecutive-failure streak stops the run early (logged clearly) rather than looping through a doomed remainder.
- Tests are split by `pytest.mark.integration`: unit tests run with `pytest -m "not integration"` and touch no live services; integration tests require `docker compose up -d` and a real `GROQ_API_KEY` in `.env`, and run with `pytest -m integration`. Integration tests use `tests/conftest.py`'s isolated fixtures (`test_session_factory`, `make_program`, monkeypatching the target module's `async_session_factory`) — never the production `daad_search.db.session.async_session_factory` directly.
- New Postgres table via `Base.metadata` — no migration tool exists yet, so this must be a new table (`init_db()`'s `create_all()` creates missing tables without touching existing populated ones), not new columns on `programs`.

---

### Task 1: Extraction schema

**Files:**
- Create: `src/daad_search/extraction/__init__.py`
- Create: `src/daad_search/extraction/schema.py`
- Test: `tests/test_extraction_schema.py`

**Interfaces:**
- Produces: `daad_search.extraction.schema.{SubScore, StandardizedTest, AcceptedTest, LanguageRequirement, GradeRequirement, DegreePrerequisite, EligibilityExtraction}` — all Pydantic `BaseModel` classes with the exact fields below.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction_schema.py
import pytest
from pydantic import ValidationError

from daad_search.extraction.schema import (
    AcceptedTest,
    DegreePrerequisite,
    EligibilityExtraction,
    GradeRequirement,
    LanguageRequirement,
    StandardizedTest,
    SubScore,
)


def test_eligibility_extraction_constructs_from_full_payload():
    extraction = EligibilityExtraction(
        requires_gre=True,
        requires_gmat=None,
        min_german_level=None,
        min_english_level="B2",
        extraction_confidence="high",
        degree_prerequisite=DegreePrerequisite(
            description="Three-year German Bachelor's degree",
            source_quote="University studies equivalent to a three-year German Bachelor's degree",
        ),
        grade_requirement=GradeRequirement(
            value=2.5, scale="German grading scale", source_quote="final grade 2.5 minimum"
        ),
        standardized_tests=[
            StandardizedTest(
                test="GRE",
                required=True,
                eligibility_condition="only for applicants from non-EU/EEA countries",
                subscores=[SubScore(section="Quantitative Reasoning", min_score=157.0)],
                waiver="Not required if CGPA better than 1.3",
                source_quote="GRE Revised General Test with at least 157 points",
            )
        ],
        language_requirements=[
            LanguageRequirement(
                language="English",
                level="B2",
                accepted_tests=[AcceptedTest(test_name="IELTS Academic", min_score="6.5")],
                source_quote="B2 required, please provide an official language certificate",
            )
        ],
        notes=None,
    )
    assert extraction.requires_gre is True
    assert extraction.standardized_tests[0].subscores[0].min_score == 157.0
    assert extraction.language_requirements[0].accepted_tests[0].test_name == "IELTS Academic"


def test_eligibility_extraction_defaults_optional_fields():
    extraction = EligibilityExtraction(extraction_confidence="low")
    assert extraction.requires_gre is None
    assert extraction.standardized_tests == []
    assert extraction.language_requirements == []
    assert extraction.degree_prerequisite is None


def test_extraction_confidence_rejects_invalid_value():
    with pytest.raises(ValidationError):
        EligibilityExtraction(extraction_confidence="very_high")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extraction_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.extraction'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/extraction/schema.py
from typing import Literal

from pydantic import BaseModel


class SubScore(BaseModel):
    section: str
    min_score: float


class StandardizedTest(BaseModel):
    """GRE or GMAT only -- NOT language proficiency tests (those belong under
    LanguageRequirement.accepted_tests instead)."""

    test: str  # "GRE" or "GMAT"
    required: bool
    eligibility_condition: str | None = None  # WHO/WHEN this applies, e.g. "Only required for applicants from non-EU/EEA countries" -- NOT the score thresholds
    subscores: list[SubScore] = []
    waiver: str | None = None
    source_quote: str


class AcceptedTest(BaseModel):
    """One way to satisfy a language requirement, e.g. IELTS 6.5."""

    test_name: str
    min_score: str  # kept as a string: scores vary in format (6.5, 72, "B2 First")


class LanguageRequirement(BaseModel):
    language: str  # "German" or "English"
    level: str  # CEFR code, or "none_required"
    # Alternatives -- the applicant needs to satisfy ONLY ONE of these tests,
    # not all of them. Do not treat this list as several separate mandatory
    # requirements.
    accepted_tests: list[AcceptedTest] = []
    source_quote: str


class GradeRequirement(BaseModel):
    value: float | None = None
    scale: str | None = None
    source_quote: str | None = None


class DegreePrerequisite(BaseModel):
    description: str
    source_quote: str


class EligibilityExtraction(BaseModel):
    """Structured eligibility criteria extracted from a DAAD program's raw
    admission-requirements and language-requirement text."""

    requires_gre: bool | None = None
    requires_gmat: bool | None = None
    min_german_level: str | None = None
    min_english_level: str | None = None
    extraction_confidence: Literal["high", "medium", "low"]
    degree_prerequisite: DegreePrerequisite | None = None
    grade_requirement: GradeRequirement | None = None
    standardized_tests: list[StandardizedTest] = []
    language_requirements: list[LanguageRequirement] = []
    notes: str | None = None
```

`src/daad_search/extraction/__init__.py` is empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extraction_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/extraction/__init__.py src/daad_search/extraction/schema.py tests/test_extraction_schema.py
git commit -m "feat: eligibility extraction Pydantic schema"
```

---

### Task 2: Eligibility Postgres table & upsert

**Files:**
- Modify: `src/daad_search/db/models.py`
- Modify: `src/daad_search/db/upsert.py`
- Test: `tests/test_eligibility_upsert.py`

**Interfaces:**
- Consumes: `daad_search.db.models.Base`, `Program` (existing); `tests/conftest.py`'s `seeded_session_factory` fixture (existing)
- Produces: `daad_search.db.models.Eligibility` (ORM class — columns: `program_id, requires_gre, requires_gmat, min_german_level, min_english_level, min_grade_value, min_grade_scale_note, extraction_confidence, structured_eligibility, extracted_at`); `async def daad_search.db.upsert.upsert_eligibility(session: AsyncSession, program_id: int, values: dict) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eligibility_upsert.py
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility
from daad_search.db.upsert import upsert_eligibility

pytestmark = pytest.mark.integration


def _values(confidence: str) -> dict:
    return dict(
        requires_gre=True,
        requires_gmat=None,
        min_german_level=None,
        min_english_level="B2",
        min_grade_value=2.5,
        min_grade_scale_note="German grading scale",
        extraction_confidence=confidence,
        structured_eligibility={"notes": "test"},
        extracted_at=datetime.now(timezone.utc),
    )


@pytest.mark.seed_programs([{"id": 1, "course_name": "Test Program", "link": "https://example.com/1"}])
async def test_upsert_inserts_then_updates_without_duplicating(seeded_session_factory):
    async with seeded_session_factory() as session:
        await upsert_eligibility(session, 1, _values("high"))

    async with seeded_session_factory() as session:
        row = (
            await session.execute(select(Eligibility).where(Eligibility.program_id == 1))
        ).scalar_one()
        assert row.extraction_confidence == "high"

    async with seeded_session_factory() as session:
        await upsert_eligibility(session, 1, _values("low"))

    async with seeded_session_factory() as session:
        rows = (
            (await session.execute(select(Eligibility).where(Eligibility.program_id == 1)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].extraction_confidence == "low"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_eligibility_upsert.py -v -m integration`
Expected: FAIL with `ImportError: cannot import name 'Eligibility' from 'daad_search.db.models'`

- [ ] **Step 3: Write the implementation**

In `src/daad_search/db/models.py`, change the import line and append the new class after `Program`:

```python
# src/daad_search/db/models.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    course_name: Mapped[str] = mapped_column(Text)
    course_name_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    university: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_type: Mapped[int] = mapped_column(Integer)
    degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[str | None] = mapped_column(Text, nullable=True)
    beginning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tuition_fees_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_tuition_fees: Mapped[bool] = mapped_column(Boolean, default=True)
    application_deadline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str] = mapped_column(Text)
    raw_sections: Mapped[dict] = mapped_column(JSONB, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_programs_subject", "subject"),
        Index("ix_programs_languages", "languages", postgresql_using="gin"),
        Index("ix_programs_has_tuition_fees", "has_tuition_fees"),
        Index("ix_programs_course_type", "course_type"),
        Index("ix_programs_city", "city"),
    )


class Eligibility(Base):
    __tablename__ = "eligibility"

    program_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("programs.id"), primary_key=True, autoincrement=False
    )
    requires_gre: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requires_gmat: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    min_german_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_english_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_grade_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_grade_scale_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(Text)
    structured_eligibility: Mapped[dict] = mapped_column(JSONB, default=dict)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_eligibility_requires_gre", "requires_gre"),
        Index("ix_eligibility_requires_gmat", "requires_gmat"),
        Index("ix_eligibility_min_german_level", "min_german_level"),
        Index("ix_eligibility_min_english_level", "min_english_level"),
    )
```

In `src/daad_search/db/upsert.py`, change the import line and append the new function:

```python
# src/daad_search/db/upsert.py
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Eligibility, Program


async def upsert_program(session: AsyncSession, program_id: int, values: dict) -> None:
    stmt = pg_insert(Program).values(id=program_id, **values)
    update_cols = {col: stmt.excluded[col] for col in values}
    stmt = stmt.on_conflict_do_update(index_elements=[Program.id], set_=update_cols)
    await session.execute(stmt)
    await session.commit()


async def upsert_eligibility(session: AsyncSession, program_id: int, values: dict) -> None:
    stmt = pg_insert(Eligibility).values(program_id=program_id, **values)
    update_cols = {col: stmt.excluded[col] for col in values}
    stmt = stmt.on_conflict_do_update(index_elements=[Eligibility.program_id], set_=update_cols)
    await session.execute(stmt)
    await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_eligibility_upsert.py -v -m integration`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/db/models.py src/daad_search/db/upsert.py tests/test_eligibility_upsert.py
git commit -m "feat: eligibility table and idempotent upsert"
```

---

### Task 3: Extractor — LangChain + Groq structured extraction

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/daad_search/config.py`
- Create: `src/daad_search/extraction/extractor.py`
- Test: `tests/test_extractor.py`

**Interfaces:**
- Consumes: `daad_search.extraction.schema.EligibilityExtraction` (Task 1); `daad_search.config.settings`
- Produces: `def daad_search.extraction.extractor.build_prompt(course_name: str, university: str, raw_sections: dict) -> str`; `def get_extraction_llm() -> ChatGroq`; `def extract_eligibility(course_name: str, university: str, raw_sections: dict) -> EligibilityExtraction`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extractor.py
import pytest

from daad_search.extraction.extractor import build_prompt, extract_eligibility


def test_build_prompt_includes_course_and_university():
    prompt = build_prompt("Additive Manufacturing", "Paderborn University", {})
    assert "Additive Manufacturing" in prompt
    assert "Paderborn University" in prompt


def test_build_prompt_falls_back_when_sections_missing():
    prompt = build_prompt("Test Course", "Test University", {})
    assert "(not stated)" in prompt


def test_build_prompt_includes_provided_raw_sections():
    raw_sections = {
        "admission_requirements": "Bachelor's degree required",
        "german_language": "No minimum level",
        "english_language": "B2 required",
    }
    prompt = build_prompt("Test Course", "Test University", raw_sections)
    assert "Bachelor's degree required" in prompt
    assert "No minimum level" in prompt
    assert "B2 required" in prompt


@pytest.mark.integration
def test_extract_eligibility_captures_conditional_gre_waiver():
    raw_sections = {
        "admission_requirements": (
            "University studies equivalent to a three-year German Bachelor's degree, "
            "final grade 2.5 minimum\n"
            "Further requirements only for applicants from non-EU/EEA countries:\n"
            'GRE Revised General Test with at least 157 points in the "Quantitative '
            'Reasoning" section and at least 4.0 points in the "Analytical Writing" '
            "section\n"
            "Applicants with a CGPA in their Bachelor's degree better than 1.3 according "
            "to the German grading scale do not need to submit the GRE."
        ),
        "german_language": "No minimum language level required",
        "english_language": (
            "B2 required, please provide an official language certificate, e.g.: "
            "Cambridge English Qualifications: B2 First, IELTS Academic: 6.5"
        ),
    }
    result = extract_eligibility("Additive Manufacturing", "Paderborn University", raw_sections)

    assert result.requires_gre is True
    assert result.grade_requirement.value == 2.5
    gre = result.standardized_tests[0]
    assert gre.test == "GRE"
    assert "1.3" in gre.waiver
    assert len(result.language_requirements) == 1
    assert result.language_requirements[0].level == "B2"


@pytest.mark.integration
def test_extract_eligibility_does_not_mark_alternative_tests_as_all_required():
    raw_sections = {
        "admission_requirements": "Bachelor's degree",
        "german_language": "No minimum language level required",
        "english_language": (
            "B2 required, please provide an official language certificate, e.g.: "
            "TOEIC: 785, TOEFL iBT (before 2026): 72, IELTS Academic: 6, "
            "Cambridge English Qualifications: B2 First"
        ),
    }
    result = extract_eligibility(
        "International Relations and Cultural Diplomacy", "Furtwangen University", raw_sections
    )

    assert result.standardized_tests == []
    english = next(lr for lr in result.language_requirements if lr.language == "English")
    assert len(english.accepted_tests) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.extraction.extractor'`

- [ ] **Step 3: Write the implementation**

Add `langchain-groq` to `pyproject.toml`'s `dependencies` list (after `voyageai`):

```toml
    "voyageai>=0.2",
    "sentence-transformers>=3.0",
    "langchain-groq>=0.2",
```

Run `uv sync --extra dev` after this edit so the dependency is actually installed and locked.

Add `groq_api_key` to `src/daad_search/config.py`, right after `voyage_api_key`:

```python
    voyage_api_key: str = ""
    groq_api_key: str = ""
```

```python
# src/daad_search/extraction/extractor.py
from langchain_groq import ChatGroq

from ..config import settings
from .schema import EligibilityExtraction

EXTRACTION_MODEL = "llama-3.3-70b-versatile"

_llm: ChatGroq | None = None

PROMPT_TEMPLATE = """You are extracting structured eligibility criteria for a German university master's program, from DAAD's own program description text. Extract ONLY what is stated or clearly implied in the text below -- do not invent requirements. If something is not mentioned, leave it null/empty rather than guessing.

Every claim you extract must include a verbatim source_quote copied exactly from the text below. A source_quote must be a SELF-CONTAINED excerpt long enough to stand on its own as a citation -- include the surrounding sentence or list block it came from, not just an isolated word or number. For example, for a language requirement, quote the whole line listing the level and the accepted certificates together (e.g. "B2 required, please provide an official language certificate, e.g.: IELTS Academic: 6.5"), not just "B2" alone.

IMPORTANT distinctions:
- standardized_tests is ONLY for academic aptitude tests (GRE, GMAT). Language proficiency tests (IELTS, TOEFL, TOEIC, Cambridge, PTE, DSH, TestDaF, etc.) belong under language_requirements.accepted_tests instead, never in standardized_tests.
- When a language section lists several accepted tests (e.g. "TOEIC: 785, TOEFL: 72, IELTS: 6"), these are ALTERNATIVES -- the applicant only needs ONE of them, not all. List each as one entry in accepted_tests; do not imply they are all separately required.
- On a StandardizedTest, eligibility_condition means WHO or WHEN this test applies (e.g. "only for applicants from non-EU/EEA countries"), NOT the score thresholds themselves (those go in subscores).

Course: {course_name}
University: {university}

--- Academic admission requirements ---
{admission_requirements}

--- German language skills ---
{german_language}

--- English language skills ---
{english_language}
"""


def build_prompt(course_name: str, university: str, raw_sections: dict) -> str:
    return PROMPT_TEMPLATE.format(
        course_name=course_name,
        university=university,
        admission_requirements=raw_sections.get("admission_requirements", "(not stated)"),
        german_language=raw_sections.get("german_language", "(not stated)"),
        english_language=raw_sections.get("english_language", "(not stated)"),
    )


def get_extraction_llm() -> ChatGroq:
    """Process-wide Groq client (constructing one per call leaks connections)."""
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=EXTRACTION_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=3
        )
    return _llm


def extract_eligibility(course_name: str, university: str, raw_sections: dict) -> EligibilityExtraction:
    prompt = build_prompt(course_name, university, raw_sections)
    structured_llm = get_extraction_llm().with_structured_output(EligibilityExtraction)
    return structured_llm.invoke(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extractor.py -v -m "not integration"` (unit tests, 3 passed)
Then: `.venv/bin/python -m pytest tests/test_extractor.py -v -m integration` (requires `GROQ_API_KEY` in `.env`, 2 passed)
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/daad_search/config.py src/daad_search/extraction/extractor.py tests/test_extractor.py
git commit -m "feat: Groq + LangChain eligibility extractor"
```

---

### Task 4: Extraction pipeline orchestration & CLI

**Files:**
- Create: `src/daad_search/extraction/pipeline.py`
- Modify: `src/daad_search/cli.py`
- Test: `tests/test_extraction_pipeline_unit.py`
- Test: `tests/test_extraction_pipeline_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1-3 (`EligibilityExtraction`, `extract_eligibility`, `Eligibility`, `upsert_eligibility`, `async_session_factory`, `Program`)
- Produces: `async def daad_search.extraction.pipeline.select_candidates(session: AsyncSession, limit_ids: list[int] | None = None, limit: int | None = None) -> list[Program]`; `async def daad_search.extraction.pipeline.extract_program(program: Program) -> tuple[int, bool]`; `async def daad_search.extraction.pipeline.run_extraction(limit_ids: list[int] | None = None, limit: int | None = None) -> dict` returning `{"total_candidates": int, "succeeded": int, "failed_ids": list[int], "stopped_early": bool}`; CLI: `python -m daad_search.cli extract [--ids ID ...] [--limit N]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extraction_pipeline_unit.py
from datetime import datetime, timezone

from daad_search.db.models import Program
from daad_search.extraction import pipeline as pipeline_module


def _program(program_id: int) -> Program:
    return Program(
        id=program_id, course_name="Test", course_name_short="Test", university="Test University",
        city="Berlin", languages=["English"], subject="Computer Science", course_type=2,
        degree="Master of Science", duration="4 semesters", beginning="Winter semester",
        tuition_fees_text="No tuition fees", has_tuition_fees=False,
        application_deadline_text="15 July", link="https://example.com",
        raw_sections={"admission_requirements": "Bachelor's degree"},
        scraped_at=datetime.now(timezone.utc),
    )


async def test_extract_program_isolates_extraction_failure(monkeypatch):
    def fake_extract_eligibility(course_name, university, raw_sections):
        raise RuntimeError("LLM error")

    monkeypatch.setattr(pipeline_module, "extract_eligibility", fake_extract_eligibility)

    program_id, ok = await pipeline_module.extract_program(_program(1))
    assert ok is False
    assert program_id == 1


async def test_process_candidates_stops_after_consecutive_failure_limit(monkeypatch):
    programs = [_program(i) for i in range(1, 11)]
    call_count = {"n": 0}

    async def fake_extract_program(program):
        call_count["n"] += 1
        return program.id, False

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs)

    assert result["stopped_early"] is True
    assert call_count["n"] == pipeline_module.CONSECUTIVE_FAILURE_LIMIT
    assert len(result["failed_ids"]) == pipeline_module.CONSECUTIVE_FAILURE_LIMIT


async def test_process_candidates_resets_consecutive_count_on_success(monkeypatch):
    programs = [_program(i) for i in range(1, 8)]
    # Fail, fail, succeed, fail, fail, succeed, fail -- never 5 in a row.
    outcomes = [False, False, True, False, False, True, False]

    async def fake_extract_program(program):
        return program.id, outcomes[program.id - 1]

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs)

    assert result["stopped_early"] is False
    assert result["succeeded"] == 2
    assert len(result["failed_ids"]) == 5
    assert result["total_candidates"] == 7
```

```python
# tests/test_extraction_pipeline_integration.py
import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility
from daad_search.extraction import pipeline as pipeline_module
from daad_search.extraction.pipeline import run_extraction

pytestmark = pytest.mark.integration

# Real DAAD admission text -- the same programs validated live during design:
# a complex conditional GRE waiver, and a plain CGPA-only case.
ADDITIVE_MANUFACTURING_SECTIONS = {
    "admission_requirements": (
        "University studies equivalent to a three-year German Bachelor's degree, "
        "final grade 2.5 minimum\n"
        "Further requirements only for applicants from non-EU/EEA countries:\n"
        'GRE Revised General Test with at least 157 points in the "Quantitative '
        'Reasoning" section and at least 4.0 points in the "Analytical Writing" '
        "section\n"
        "Applicants with a CGPA in their Bachelor's degree better than 1.3 according "
        "to the German grading scale do not need to submit the GRE."
    ),
    "german_language": "No minimum language level required",
    "english_language": (
        "B2 required, please provide an official language certificate, e.g.: "
        "Cambridge English Qualifications: B2 First, IELTS Academic: 6.5"
    ),
}
IOT_SECTIONS = {
    "admission_requirements": (
        "A completed Bachelor's degree in computer science, computer engineering or "
        "a related field\n"
        "A minimum CGPA (cumulative grade point average) of 2.5 (according to the "
        "German grading system) or higher\n"
        "English language skills at level B2 (see below)"
    ),
    "english_language": "PTE Academic: 60, IELTS Academic: 6",
}


@pytest.fixture
def extraction_env(monkeypatch, test_session_factory):
    """Point run_extraction at the test database."""
    monkeypatch.setattr(pipeline_module, "async_session_factory", test_session_factory)
    return test_session_factory


async def test_run_extraction_populates_eligibility_table(extraction_env, make_program):
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=10396, course_name="Additive Manufacturing", university="Paderborn University",
                link="https://example.com/10396", raw_sections=ADDITIVE_MANUFACTURING_SECTIONS,
            ),
            make_program(
                id=9012, course_name="Computer Engineering for IoT Systems",
                university="Nordhausen University of Applied Sciences",
                link="https://example.com/9012", raw_sections=IOT_SECTIONS,
            ),
            make_program(
                id=1, course_name="No admission text", university="Test University",
                link="https://example.com/1",
                raw_sections={"description": "no eligibility text here"},
            ),
        ])
        await session.commit()

    result = await run_extraction()

    # Program 1 has none of the 3 relevant keys -- excluded as a candidate.
    assert result["total_candidates"] == 2
    assert result["succeeded"] == 2
    assert result["failed_ids"] == []

    async with session_factory() as session:
        rows = (await session.execute(select(Eligibility))).scalars().all()
        by_id = {row.program_id: row for row in rows}

    assert set(by_id.keys()) == {10396, 9012}
    assert by_id[10396].requires_gre is True
    assert by_id[10396].min_grade_value == 2.5
    assert "1.3" in by_id[10396].structured_eligibility["standardized_tests"][0]["waiver"]


async def test_run_extraction_is_idempotent_on_rerun(extraction_env, make_program):
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=10396, course_name="Additive Manufacturing", university="Paderborn University",
                link="https://example.com/10396", raw_sections=ADDITIVE_MANUFACTURING_SECTIONS,
            ),
        ])
        await session.commit()

    first = await run_extraction()
    assert first["total_candidates"] == 1
    assert first["succeeded"] == 1

    second = await run_extraction()
    assert second["total_candidates"] == 0  # already has an eligibility row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extraction_pipeline_unit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.extraction.pipeline'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/extraction/pipeline.py
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Eligibility, Program
from ..db.session import async_session_factory
from ..db.upsert import upsert_eligibility
from .extractor import extract_eligibility

logger = logging.getLogger(__name__)

CONSECUTIVE_FAILURE_LIMIT = 5


async def select_candidates(
    session: AsyncSession, limit_ids: list[int] | None = None, limit: int | None = None
) -> list[Program]:
    stmt = (
        select(Program)
        .outerjoin(Eligibility, Eligibility.program_id == Program.id)
        .where(Eligibility.program_id.is_(None))
        .where(
            Program.raw_sections.has_key("admission_requirements")
            | Program.raw_sections.has_key("german_language")
            | Program.raw_sections.has_key("english_language")
        )
        .order_by(Program.id)
    )
    if limit_ids is not None:
        stmt = stmt.where(Program.id.in_(limit_ids))
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def extract_program(program: Program) -> tuple[int, bool]:
    try:
        result = await asyncio.to_thread(
            extract_eligibility, program.course_name, program.university, program.raw_sections
        )
    except Exception:
        logger.exception("Failed to extract eligibility for program %s", program.id)
        return program.id, False

    values = dict(
        requires_gre=result.requires_gre,
        requires_gmat=result.requires_gmat,
        min_german_level=result.min_german_level,
        min_english_level=result.min_english_level,
        min_grade_value=result.grade_requirement.value if result.grade_requirement else None,
        min_grade_scale_note=result.grade_requirement.scale if result.grade_requirement else None,
        extraction_confidence=result.extraction_confidence,
        structured_eligibility=result.model_dump(),
        extracted_at=datetime.now(timezone.utc),
    )

    try:
        async with async_session_factory() as session:
            await upsert_eligibility(session, program.id, values)
    except Exception:
        logger.exception("Failed to store eligibility for program %s", program.id)
        return program.id, False

    return program.id, True


async def _process_candidates(candidates: list[Program]) -> dict:
    """Extract eligibility for each candidate in order, stopping early after
    CONSECUTIVE_FAILURE_LIMIT failures in a row (a strong signal of quota
    exhaustion, not per-program bad luck)."""
    succeeded_ids: list[int] = []
    failed_ids: list[int] = []
    consecutive_failures = 0
    stopped_early = False

    for program in candidates:
        program_id, ok = await extract_program(program)
        if ok:
            succeeded_ids.append(program_id)
            consecutive_failures = 0
        else:
            failed_ids.append(program_id)
            consecutive_failures += 1
            if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                logger.error(
                    "Stopping early after %d consecutive failures (likely quota exhausted)",
                    consecutive_failures,
                )
                stopped_early = True
                break

    return {
        "total_candidates": len(candidates),
        "succeeded": len(succeeded_ids),
        "failed_ids": failed_ids,
        "stopped_early": stopped_early,
    }


async def run_extraction(limit_ids: list[int] | None = None, limit: int | None = None) -> dict:
    async with async_session_factory() as session:
        candidates = await select_candidates(session, limit_ids=limit_ids, limit=limit)
    return await _process_candidates(candidates)
```

Modify `src/daad_search/cli.py`:

```python
# src/daad_search/cli.py
import argparse
import asyncio
import logging

from .db.session import init_db
from .extraction.pipeline import run_extraction
from .ingestion.pipeline import run_ingestion


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="daad-search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create Postgres tables")

    ingest_parser = subparsers.add_parser("ingest", help="Run the full ingestion pipeline")
    ingest_parser.add_argument(
        "--ids", type=int, nargs="*", default=None,
        help="Only ingest these DAAD program IDs (for testing)",
    )
    ingest_parser.add_argument(
        "--refresh", action="store_true",
        help="Ignore cached DAAD responses and re-fetch everything for this run",
    )

    extract_parser = subparsers.add_parser(
        "extract", help="Extract structured eligibility criteria for programs missing it"
    )
    extract_parser.add_argument(
        "--ids", type=int, nargs="*", default=None,
        help="Only extract these DAAD program IDs (for testing)",
    )
    extract_parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most this many programs this run (e.g. to respect a daily quota)",
    )

    args = parser.parse_args()

    if args.command == "init-db":
        asyncio.run(init_db())
    elif args.command == "ingest":
        result = asyncio.run(run_ingestion(limit_ids=args.ids, refresh=args.refresh))
        print(
            f"Ingested {result['succeeded']}/{result['total']} programs. "
            f"Failed IDs: {result['failed_ids']}"
        )
        print(
            f"Embedded {result['embedded']}/{result['succeeded']} programs. "
            f"Embedding failures: {len(result['embedding_failed_ids'])} "
            f"{result['embedding_failed_ids']}"
        )
        if result["reconciled_ids"]:
            print(
                f"Reconciled away {len(result['reconciled_ids'])} programs "
                f"no longer listed by DAAD: {result['reconciled_ids']}"
            )
    elif args.command == "extract":
        result = asyncio.run(run_extraction(limit_ids=args.ids, limit=args.limit))
        print(
            f"Extracted eligibility for {result['succeeded']}/{result['total_candidates']} "
            f"candidate programs. Failed IDs: {result['failed_ids']}"
        )
        if result["stopped_early"]:
            print(
                "Stopped early after repeated consecutive failures (likely quota exhausted). "
                "Re-run `extract` later to resume."
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extraction_pipeline_unit.py -v -m "not integration"`
Expected: PASS (3 passed)

Run: `.venv/bin/python -m pytest tests/test_extraction_pipeline_integration.py -v -m integration` (requires `GROQ_API_KEY`, real Groq calls)
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/extraction/pipeline.py src/daad_search/cli.py tests/test_extraction_pipeline_unit.py tests/test_extraction_pipeline_integration.py
git commit -m "feat: eligibility extraction pipeline orchestration and CLI"
```

---

## Final Verification

After Task 4, run the whole suite:

```bash
.venv/bin/python -m pytest -v -m "not integration"   # fast unit tests, no services needed
.venv/bin/python -m pytest -v -m integration          # requires: docker compose up -d, .env with GROQ_API_KEY
```

Then run extraction against a few real programs and inspect the result:

```bash
.venv/bin/python -m daad_search.cli extract --ids 10396 9012
docker exec data-foundation-postgres-1 psql -U daad -d daad -x -c \
  "SELECT * FROM eligibility WHERE program_id IN (10396, 9012);"
```

Once satisfied, run a full extraction pass (auto-resumable — safe to re-run if it stops early on quota):

```bash
.venv/bin/python -m daad_search.cli extract --limit 900
```

At this point the eligibility-extraction spec is fully implemented: every program with admission text has (or can get, via a resumed `extract` run) structured, citation-backed eligibility criteria in Postgres, ready for the query-understanding spec to reason over.
