# Query Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `POST /query` endpoint that parses a free-text query into search filters + a student profile, runs the existing hybrid search, and batches eligibility reasoning over the top candidates against spec 2's structured eligibility data — with a 3-tier automatic LLM provider fallback (Groq → Mistral → Gemini) and application-level graceful degradation if all three fail.

**Architecture:** A new `query_understanding/` package (schemas, a shared fallback-chain builder, a query parser, an eligibility reasoner) parallel to the existing `extraction/` package. A new `api/query.py` orchestrates: parse → search (reusing spec 1's `filtered_search`/`hybrid_search` in-process) → split top-10 by eligibility-data availability → batch-reason → merge verdicts.

**Tech Stack:** LangChain (`langchain-groq`, `langchain-mistralai`, `langchain-google-genai`) with `.with_fallbacks()`. Reuses spec 1's FastAPI/SQLAlchemy stack and spec 2's `Eligibility` table.

## Global Constraints

- Python 3.11+, `src/` package layout, native `T | None` union syntax — no `Optional[T]`, no `from __future__ import annotations`. Always verify with `.venv/bin/python --version` (should print `Python 3.11.15`) before running anything — bare `python3` on this machine resolves to system Python 3.9.6, which has broken prior implementers on this project multiple times.
- Both LLM calls (`parse_query`, `reason_about_eligibility`) are **synchronous** functions (the underlying `ChatGroq`/`ChatMistralAI`/`ChatGoogleGenerativeAI` clients are sync, same as `voyageai`/`qdrant-client` elsewhere in this codebase). Any call to them from async code (the orchestration layer, Task 5) is out of scope for this plan's tasks 1-4 — Task 5 wraps them itself where needed.
- The fallback chain is Groq → Mistral → Gemini, in that exact order, built once per Pydantic schema via LangChain's `.with_fallbacks()`. `OPENAI_API_KEY` exists in config but must never be read by the automatic chain — it's a manual-override-only setting, out of scope for this plan.
- `"no_data"` is never an LLM-producible value for `EligibilityVerdict.verdict` (which only has 4 values: `eligible`, `likely_eligible`, `not_eligible`, `unclear`) — it's assigned deterministically by the orchestration layer for candidates with no `Eligibility` row or past the reasoning cutoff.
- Grade-scale comparison is done by LLM judgment inside the reasoning prompt — no hand-coded conversion formula anywhere in this plan.
- Eligibility reasoning is capped at `min(10, limit)` candidates per query, regardless of how high `limit` is set.
- `/query`'s `limit` field mirrors `/search`'s exactly: `Field(20, ge=1, le=100)`.
- Tests are split by `pytest.mark.integration`: unit tests run with `pytest -m "not integration"` and touch no live services; integration tests require `docker compose up -d` and real `GROQ_API_KEY`/`MISTRAL_API_KEY`/`GEMINI_API_KEY` in `.env`, and use `tests/conftest.py`'s isolated fixtures (`test_session_factory`, `seeded_session_factory`, `test_qdrant`, `api_client`) — never production settings directly.

## File Structure

- `src/daad_search/query_understanding/__init__.py` — empty (Task 1)
- `src/daad_search/query_understanding/schema.py` — `StudentProfile`, `ParsedQuery`, `EligibilityVerdict`, `BatchEligibilityReasoning`, `CandidateForReasoning` (Task 1); gains `QueryRequest`, `QueryResult`, `QueryResponse` (Task 5)
- `src/daad_search/query_understanding/llm.py` — `get_fallback_llm(schema)` (Task 2)
- `src/daad_search/query_understanding/parser.py` — `build_query_prompt`, `parse_query` (Task 3)
- `src/daad_search/query_understanding/reasoner.py` — `build_reasoning_prompt`, `reason_about_eligibility` (Task 4)
- `src/daad_search/api/query.py` — `handle_query` orchestration (Task 5)
- `src/daad_search/api/main.py` — gains `POST /query` route (Task 5)
- `src/daad_search/config.py` — gains `mistral_api_key`, `gemini_api_key`, `openai_api_key` (Task 2)
- `pyproject.toml` — gains `langchain-mistralai`, `langchain-google-genai` (Task 2)

---

### Task 1: Query understanding schemas

**Files:**
- Create: `src/daad_search/query_understanding/__init__.py`
- Create: `src/daad_search/query_understanding/schema.py`
- Test: `tests/test_query_understanding_schema.py`

**Interfaces:**
- Consumes: `daad_search.api.schemas.SearchFilters` (existing)
- Produces: `daad_search.query_understanding.schema.{StudentProfile, ParsedQuery, EligibilityVerdict, BatchEligibilityReasoning, CandidateForReasoning}` — all Pydantic `BaseModel` classes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_understanding_schema.py
import pytest
from pydantic import ValidationError

from daad_search.api.schemas import SearchFilters
from daad_search.query_understanding.schema import (
    BatchEligibilityReasoning,
    CandidateForReasoning,
    EligibilityVerdict,
    ParsedQuery,
    StudentProfile,
)


def test_parsed_query_constructs_from_full_payload():
    parsed = ParsedQuery(
        filters=SearchFilters(languages=["English"], max_tuition_free_only=True),
        semantic_query="machine learning and robotics",
        student_profile=StudentProfile(
            degree_field="Artificial Intelligence",
            grade_value=3.2,
            grade_scale="4.0 GPA scale (USA)",
            nationality="Pakistan",
        ),
    )
    assert parsed.filters.languages == ["English"]
    assert parsed.student_profile.grade_value == 3.2


def test_student_profile_defaults_all_fields_to_none():
    profile = StudentProfile()
    assert profile.degree_field is None
    assert profile.grade_value is None
    assert profile.nationality is None


def test_eligibility_verdict_rejects_invalid_verdict_value():
    with pytest.raises(ValidationError):
        EligibilityVerdict(program_id=1, verdict="maybe", reasoning="unsure")


def test_eligibility_verdict_rejects_no_data_as_llm_value():
    """no_data is assigned by the orchestration layer, never by the LLM."""
    with pytest.raises(ValidationError):
        EligibilityVerdict(program_id=1, verdict="no_data", reasoning="n/a")


def test_batch_eligibility_reasoning_defaults_to_empty_list():
    batch = BatchEligibilityReasoning()
    assert batch.verdicts == []


def test_candidate_for_reasoning_constructs():
    candidate = CandidateForReasoning(
        program_id=10396, course_name="Additive Manufacturing",
        structured_eligibility={"grade_requirement": {"value": 2.5}},
    )
    assert candidate.program_id == 10396
    assert candidate.structured_eligibility["grade_requirement"]["value"] == 2.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_query_understanding_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.query_understanding'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/query_understanding/schema.py
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
```

`src/daad_search/query_understanding/__init__.py` is empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_query_understanding_schema.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/query_understanding/__init__.py src/daad_search/query_understanding/schema.py tests/test_query_understanding_schema.py
git commit -m "feat: query understanding schemas"
```

---

### Task 2: LLM fallback chain infrastructure

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/daad_search/config.py`
- Create: `src/daad_search/query_understanding/llm.py`
- Test: `tests/test_query_understanding_llm.py`

**Interfaces:**
- Consumes: `daad_search.config.settings`
- Produces: `def daad_search.query_understanding.llm.get_fallback_llm(schema: type[BaseModel]) -> Runnable` — a Groq→Mistral→Gemini structured-output fallback chain for the given schema, cached per schema class.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_understanding_llm.py
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel


class DummySchema(BaseModel):
    value: str


def _fake_llm(name: str, should_fail: bool):
    calls: list[str] = []

    def _invoke(prompt):
        calls.append(prompt)
        if should_fail:
            raise RuntimeError(f"{name} failed")
        return f"{name} result"

    return RunnableLambda(_invoke), calls


class _FakeChatModel:
    def __init__(self, runnable):
        self._runnable = runnable

    def with_structured_output(self, schema):
        return self._runnable


def _patch_providers(monkeypatch, llm_module, primary_fails: bool, secondary_fails: bool):
    primary, primary_calls = _fake_llm("primary", should_fail=primary_fails)
    secondary, secondary_calls = _fake_llm("secondary", should_fail=secondary_fails)
    tertiary, tertiary_calls = _fake_llm("tertiary", should_fail=False)

    monkeypatch.setattr(llm_module, "ChatGroq", lambda **kw: _FakeChatModel(primary))
    monkeypatch.setattr(llm_module, "ChatMistralAI", lambda **kw: _FakeChatModel(secondary))
    monkeypatch.setattr(llm_module, "ChatGoogleGenerativeAI", lambda **kw: _FakeChatModel(tertiary))
    monkeypatch.setattr(llm_module, "_chains", {})

    return primary_calls, secondary_calls, tertiary_calls


def test_fallback_chain_falls_through_to_secondary_when_primary_fails(monkeypatch):
    from daad_search.query_understanding import llm as llm_module

    primary_calls, secondary_calls, tertiary_calls = _patch_providers(
        monkeypatch, llm_module, primary_fails=True, secondary_fails=False
    )

    chain = llm_module.get_fallback_llm(DummySchema)
    result = chain.invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == []
    assert result == "secondary result"


def test_fallback_chain_falls_through_to_tertiary_when_first_two_fail(monkeypatch):
    from daad_search.query_understanding import llm as llm_module

    primary_calls, secondary_calls, tertiary_calls = _patch_providers(
        monkeypatch, llm_module, primary_fails=True, secondary_fails=True
    )

    chain = llm_module.get_fallback_llm(DummySchema)
    result = chain.invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == ["test prompt"]
    assert result == "tertiary result"


def test_get_fallback_llm_caches_per_schema(monkeypatch):
    from daad_search.query_understanding import llm as llm_module

    _patch_providers(monkeypatch, llm_module, primary_fails=False, secondary_fails=False)

    first = llm_module.get_fallback_llm(DummySchema)
    second = llm_module.get_fallback_llm(DummySchema)
    assert first is second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_query_understanding_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.query_understanding.llm'`

- [ ] **Step 3: Write the implementation**

Add `langchain-mistralai` and `langchain-google-genai` to `pyproject.toml`'s `dependencies` list (after `langchain-groq`):

```toml
    "langchain-groq>=0.2",
    "langchain-mistralai>=0.2",
    "langchain-google-genai>=2.0",
```

Run `uv sync --extra dev` after this edit so both are actually installed and locked.

Add three fields to `src/daad_search/config.py`, right after the existing `groq_api_key: str = ""` line:

```python
    groq_api_key: str = ""
    mistral_api_key: str = ""
    gemini_api_key: str = ""
    # Available for a manual, explicit override only -- NEVER read by the
    # automatic Groq -> Mistral -> Gemini fallback chain in
    # query_understanding/llm.py. Wiring a paid provider into an automatic
    # chain risks incurring real charges the moment the free tiers are
    # exhausted, without anyone choosing that to happen.
    openai_api_key: str = ""
```

```python
# src/daad_search/query_understanding/llm.py
from typing import TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..config import settings

GROQ_MODEL = "llama-3.3-70b-versatile"
MISTRAL_MODEL = "mistral-small-latest"
GEMINI_MODEL = "gemini-2.0-flash"

T = TypeVar("T", bound=BaseModel)

_chains: dict[type[BaseModel], object] = {}


def get_fallback_llm(schema: type[T]):
    """Groq -> Mistral -> Gemini structured-output fallback chain for `schema`.

    Cached per schema class (constructing 3 clients per call would leak
    connections). All three providers are free-tier; if the primary fails
    (rate limit, network error, malformed output), LangChain's
    `.with_fallbacks()` transparently tries the next one with the same
    prompt/schema.
    """
    if schema not in _chains:
        primary = ChatGroq(
            model=GROQ_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        secondary = ChatMistralAI(
            model=MISTRAL_MODEL, api_key=settings.mistral_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        tertiary = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, api_key=settings.gemini_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        _chains[schema] = primary.with_fallbacks([secondary, tertiary])
    return _chains[schema]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_query_understanding_llm.py -v`
Expected: PASS (3 passed). These are unit tests (mocked providers) — no `pytest.mark.integration`, no live API calls.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/daad_search/config.py src/daad_search/query_understanding/llm.py tests/test_query_understanding_llm.py
git commit -m "feat: Groq/Mistral/Gemini fallback chain infrastructure"
```

---

### Task 3: Query parser

**Files:**
- Create: `src/daad_search/query_understanding/parser.py`
- Test: `tests/test_query_parser.py`

**Interfaces:**
- Consumes: `daad_search.query_understanding.schema.ParsedQuery` (Task 1), `daad_search.query_understanding.llm.get_fallback_llm` (Task 2)
- Produces: `def build_query_prompt(query: str) -> str`; `def parse_query(query: str) -> ParsedQuery | None` (`None` signals total failure across all 3 providers — the orchestration layer's Layer 2 fallback trigger)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_parser.py
import pytest

from daad_search.query_understanding.parser import build_query_prompt, parse_query


def test_build_query_prompt_includes_the_raw_query():
    prompt = build_query_prompt("masters in robotics, no fee, English taught")
    assert "masters in robotics, no fee, English taught" in prompt


def test_build_query_prompt_documents_course_type_codes():
    prompt = build_query_prompt("anything")
    assert "2=Master's" in prompt


def test_parse_query_returns_none_when_all_providers_fail(monkeypatch):
    from daad_search.query_understanding import parser as parser_module

    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")

    monkeypatch.setattr(parser_module, "get_fallback_llm", lambda schema: AlwaysFailsChain())

    assert parse_query("anything") is None


@pytest.mark.integration
def test_parse_query_extracts_filters_and_student_profile():
    result = parse_query(
        "I have a bachelors in Artificial Intelligence from Pakistan with CGPA 3.2, "
        "and I want English-taught, no-fee master's programs in Germany"
    )
    assert result is not None
    assert result.filters.max_tuition_free_only is True
    assert "English" in (result.filters.languages or [])
    assert result.filters.course_type == 2
    assert result.student_profile.grade_value == 3.2
    assert result.student_profile.nationality is not None
    assert "pakistan" in result.student_profile.nationality.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_query_parser.py -v -m "not integration"`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.query_understanding.parser'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/query_understanding/parser.py
import logging

from .llm import get_fallback_llm
from .schema import ParsedQuery

logger = logging.getLogger(__name__)

QUERY_PROMPT_TEMPLATE = """You are parsing a prospective international student's free-text search query for German university study programs into structured data.

Extract THREE things from the query below:

1. filters -- hard constraints explicitly stated (only set a field if the query actually states it; leave others null):
   - languages: list of teaching languages requested, e.g. ["English"]
   - max_tuition_free_only: true if the student wants only tuition-free programs
   - subject: ONLY set this if the query names an exact, narrow academic subject that is likely to match a university subject label directly (e.g. "Mechanical Engineering"). If the subject is broad, colloquial, or might not match an exact label (e.g. "robotics", "AI", "data stuff"), leave subject null and put it in semantic_query instead -- it will be matched by meaning, not exact text.
   - city: a specific city name if mentioned
   - course_type: the DAAD numeric course type code, ONLY if the query clearly implies one: 1=Bachelor's, 2=Master's, 3=PhD, 4=Graduate school, 5=Language course, 6=Short course, 7=Preparatory course, 9=Various. Most queries about "masters" should set this to 2.

2. semantic_query -- the substantive topic/subject-matter part of the query that isn't captured as a hard filter above (e.g. "robotics", "machine learning and business analytics"). Leave null if there's no such topic beyond the filters.

3. student_profile -- facts about the STUDENT THEMSELVES (not the programs they want), only if explicitly stated:
   - degree_field: their own prior degree's field, e.g. "Artificial Intelligence"
   - grade_value: their stated grade/CGPA/GPA as a number, e.g. 3.2
   - grade_scale: how they described the scale, e.g. "4.0 GPA scale (USA)" or "percentage" -- describe it in their own terms, do not convert it
   - nationality: their stated nationality/country of origin
   - other_notes: any other fact about the student relevant to eligibility (e.g. work experience, existing test scores) that doesn't fit the above

Query: {query}
"""


def build_query_prompt(query: str) -> str:
    return QUERY_PROMPT_TEMPLATE.format(query=query)


def parse_query(query: str) -> ParsedQuery | None:
    prompt = build_query_prompt(query)
    try:
        return get_fallback_llm(ParsedQuery).invoke(prompt)
    except Exception:
        logger.exception("Failed to parse query across all LLM providers: %r", query)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_query_parser.py -v -m "not integration"` (3 unit tests)
Then: `.venv/bin/python -m pytest tests/test_query_parser.py -v -m integration` (requires `GROQ_API_KEY`/`MISTRAL_API_KEY`/`GEMINI_API_KEY` in `.env`, 1 test)
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/query_understanding/parser.py tests/test_query_parser.py
git commit -m "feat: free-text query parser"
```

---

### Task 4: Eligibility reasoner

**Files:**
- Create: `src/daad_search/query_understanding/reasoner.py`
- Test: `tests/test_eligibility_reasoner.py`

**Interfaces:**
- Consumes: `daad_search.query_understanding.schema.{StudentProfile, BatchEligibilityReasoning, CandidateForReasoning, EligibilityVerdict}` (Task 1), `daad_search.query_understanding.llm.get_fallback_llm` (Task 2)
- Produces: `def build_reasoning_prompt(profile: StudentProfile, candidates: list[CandidateForReasoning]) -> str`; `def reason_about_eligibility(profile: StudentProfile, candidates: list[CandidateForReasoning]) -> list[EligibilityVerdict] | None` (`None` signals total failure across all 3 providers; empty list input returns empty list output without any LLM call)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eligibility_reasoner.py
import pytest

from daad_search.query_understanding.reasoner import build_reasoning_prompt, reason_about_eligibility
from daad_search.query_understanding.schema import CandidateForReasoning, StudentProfile


def test_build_reasoning_prompt_includes_profile_and_candidates():
    profile = StudentProfile(grade_value=3.2, nationality="Pakistan")
    candidates = [
        CandidateForReasoning(
            program_id=10396, course_name="Additive Manufacturing",
            structured_eligibility={"foo": "bar"},
        ),
    ]
    prompt = build_reasoning_prompt(profile, candidates)
    assert "3.2" in prompt
    assert "Pakistan" in prompt
    assert "10396" in prompt
    assert "Additive Manufacturing" in prompt


def test_reason_about_eligibility_returns_empty_list_for_no_candidates():
    assert reason_about_eligibility(StudentProfile(), []) == []


def test_reason_about_eligibility_returns_none_when_all_providers_fail(monkeypatch):
    from daad_search.query_understanding import reasoner as reasoner_module

    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")

    monkeypatch.setattr(reasoner_module, "get_fallback_llm", lambda schema: AlwaysFailsChain())

    candidates = [
        CandidateForReasoning(program_id=1, course_name="Test", structured_eligibility={}),
    ]
    assert reason_about_eligibility(StudentProfile(), candidates) is None


@pytest.mark.integration
def test_reason_about_eligibility_produces_sensible_verdicts_for_real_data():
    # Real extracted eligibility for program 10396 (Additive Manufacturing):
    # grade 2.5 max (German scale), GRE required only for non-EU/EEA unless
    # CGPA better than 1.3, English B2.
    structured_eligibility = {
        "grade_requirement": {"value": 2.5, "scale": "German grading scale (1.0 best - 5.0 worst)"},
        "standardized_tests": [{
            "test": "GRE", "required": True,
            "eligibility_condition": "only for applicants from non-EU/EEA countries",
            "waiver": "Not required if CGPA better than 1.3 on the German grading scale",
        }],
        "min_english_level": "B2",
    }
    candidates = [
        CandidateForReasoning(
            program_id=10396, course_name="Additive Manufacturing",
            structured_eligibility=structured_eligibility,
        ),
    ]

    # Clearly strong profile: an excellent grade should convert well under
    # the 2.5 German-scale threshold, and be judged as waiving the GRE too.
    strong_profile = StudentProfile(
        degree_field="Mechanical Engineering", grade_value=3.9,
        grade_scale="4.0 GPA scale (USA)", nationality="Pakistan",
    )
    strong_verdicts = reason_about_eligibility(strong_profile, candidates)
    assert strong_verdicts is not None
    assert strong_verdicts[0].program_id == 10396
    assert strong_verdicts[0].verdict in ("eligible", "likely_eligible")

    # Clearly weak profile: a poor grade, well outside any waiver.
    weak_profile = StudentProfile(
        degree_field="Mechanical Engineering", grade_value=2.0,
        grade_scale="4.0 GPA scale (USA)", nationality="Pakistan",
    )
    weak_verdicts = reason_about_eligibility(weak_profile, candidates)
    assert weak_verdicts is not None
    assert weak_verdicts[0].verdict in ("not_eligible", "unclear")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_eligibility_reasoner.py -v -m "not integration"`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.query_understanding.reasoner'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_eligibility_reasoner.py -v -m "not integration"` (3 unit tests)
Then: `.venv/bin/python -m pytest tests/test_eligibility_reasoner.py -v -m integration` (1 test)
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/query_understanding/reasoner.py tests/test_eligibility_reasoner.py
git commit -m "feat: batched eligibility reasoner"
```

---

### Task 5: Orchestration & API endpoint

**Files:**
- Modify: `src/daad_search/query_understanding/schema.py`
- Create: `src/daad_search/api/query.py`
- Modify: `src/daad_search/api/main.py`
- Test: `tests/test_query_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4, plus `daad_search.api.search.{filtered_search, hybrid_search}` (spec 1), `daad_search.db.models.Eligibility` (spec 2)
- Produces: `async def daad_search.api.query.handle_query(session: AsyncSession, query: str, limit: int) -> QueryResponse`; FastAPI route `POST /query`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_query_api.py
import asyncio
from datetime import datetime, timezone

import pytest

from daad_search.api import query as query_module
from daad_search.api.schemas import SearchFilters
from daad_search.db.models import Eligibility
from daad_search.query_understanding.schema import ParsedQuery, StudentProfile

pytestmark = pytest.mark.integration


def _seed_eligibility(session_factory, program_id: int, structured_eligibility: dict) -> None:
    async def _seed() -> None:
        async with session_factory() as session:
            session.add(Eligibility(
                program_id=program_id, extraction_confidence="high",
                structured_eligibility=structured_eligibility,
                extracted_at=datetime.now(timezone.utc),
            ))
            await session.commit()

    asyncio.run(_seed())


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "subject": "Mechanical Engineering",
     "languages": ["English"], "has_tuition_fees": False, "link": "https://example.com/1"},
])
def test_query_reasoning_failure_returns_unclear_verdicts(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})

    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(subject="Mechanical Engineering"), semantic_query=None,
            student_profile=StudentProfile(nationality="Pakistan"),
        ),
    )
    monkeypatch.setattr(query_module, "reason_about_eligibility", lambda profile, candidates: None)

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    result = next(r for r in body["results"] if r["id"] == 1)
    assert result["eligibility_verdict"] == "unclear"
    assert body["extracted_filters"] is not None
    assert body["extracted_profile"]["nationality"] == "Pakistan"


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "subject": "Mechanical Engineering",
     "languages": ["English"], "has_tuition_fees": False, "link": "https://example.com/1"},
])
def test_query_candidate_with_no_eligibility_row_gets_no_data(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(subject="Mechanical Engineering"), semantic_query=None,
            student_profile=StudentProfile(nationality="Pakistan"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    result = next(r for r in body["results"] if r["id"] == 1)
    assert result["eligibility_verdict"] == "no_data"
    assert result["eligibility_reasoning"] is None
```

```python
# Append to tests/test_query_api.py -- exercises the parse-failure fallback
# path, which needs the semantic-search machinery (Qdrant), matching the
# existing tests/test_hybrid_search.py pattern.
from qdrant_client.models import PointStruct

from daad_search.api import search as search_module
from daad_search.ingestion import embeddings as embeddings_module


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_parse_failure_falls_back_to_semantic_search(api_client, test_qdrant, monkeypatch):
    test_qdrant.upsert(
        collection_name=embeddings_module.COLLECTION_NAME,
        points=[PointStruct(id=1, vector=[1.0, 0.0] + [0.0] * 1022, payload={"program_id": 1})],
        wait=True,
    )

    def fake_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [[1.0, 0.0] + [0.0] * 1022 for _ in texts]

    monkeypatch.setattr(query_module, "parse_query", lambda q: None)
    monkeypatch.setattr(search_module, "embed_texts", fake_embed)

    response = api_client.post("/query", json={"query": "Robotics Engineering MSc"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_filters"] is None
    assert body["extracted_profile"] is None
    assert any(r["id"] == 1 for r in body["results"])
    assert all(r["eligibility_verdict"] == "no_data" for r in body["results"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_query_api.py -v -m integration`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.api.query'`

- [ ] **Step 3: Write the implementation**

Append to `src/daad_search/query_understanding/schema.py` — change the import line and add three classes:

```python
from pydantic import BaseModel, Field

from ..api.schemas import SearchFilters, SearchResult
```

```python
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
```

```python
# src/daad_search/api/query.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Eligibility
from ..query_understanding.parser import parse_query
from ..query_understanding.reasoner import reason_about_eligibility
from ..query_understanding.schema import (
    CandidateForReasoning,
    EligibilityVerdict,
    QueryResponse,
    QueryResult,
)
from . import search as search_module
from .schemas import SearchFilters

REASONING_CANDIDATE_CAP = 10


async def handle_query(session: AsyncSession, query: str, limit: int) -> QueryResponse:
    parsed = parse_query(query)

    if parsed is not None:
        filters = parsed.filters
        semantic_query = parsed.semantic_query
        profile = parsed.student_profile
    else:
        # Layer 2 degradation: parsing failed on every provider -- fall back
        # to a pure semantic search over the raw query text.
        filters = SearchFilters()
        semantic_query = query
        profile = None

    if semantic_query:
        results, total = await search_module.hybrid_search(session, filters, semantic_query, limit)
    else:
        results, total = await search_module.filtered_search(session, filters, limit)

    reasoning_pool = results[:REASONING_CANDIDATE_CAP]
    remainder = results[REASONING_CANDIDATE_CAP:]

    verdicts_by_id: dict[int, EligibilityVerdict] = {}
    reasoned_ids: set[int] = set()

    if profile is not None and reasoning_pool:
        pool_ids = [r.id for r in reasoning_pool]
        eligibility_rows = (
            (await session.execute(select(Eligibility).where(Eligibility.program_id.in_(pool_ids))))
            .scalars()
            .all()
        )
        eligibility_by_id = {row.program_id: row for row in eligibility_rows}

        candidates = [
            CandidateForReasoning(
                program_id=r.id, course_name=r.course_name,
                structured_eligibility=eligibility_by_id[r.id].structured_eligibility,
            )
            for r in reasoning_pool
            if r.id in eligibility_by_id
        ]
        reasoned_ids = {c.program_id for c in candidates}

        raw_verdicts = reason_about_eligibility(profile, candidates) if candidates else []
        if raw_verdicts is not None:
            verdicts_by_id = {v.program_id: v for v in raw_verdicts}
        # else: Layer 2 degradation -- reasoning failed on every provider.
        # verdicts_by_id stays empty; every id in reasoned_ids falls through
        # to "unclear" below.

    query_results: list[QueryResult] = []
    for r in reasoning_pool:
        if r.id in verdicts_by_id:
            v = verdicts_by_id[r.id]
            verdict, reasoning = v.verdict, v.reasoning
        elif r.id in reasoned_ids:
            # Had eligibility data and was sent to the LLM, but no verdict
            # came back for it -- either the whole call failed (Layer 2), or
            # the LLM's response omitted this specific id.
            verdict, reasoning = "unclear", "Eligibility reasoning was unavailable for this program."
        else:
            verdict, reasoning = "no_data", None
        query_results.append(
            QueryResult(**r.model_dump(), eligibility_verdict=verdict, eligibility_reasoning=reasoning)
        )

    for r in remainder:
        query_results.append(
            QueryResult(**r.model_dump(), eligibility_verdict="no_data", eligibility_reasoning=None)
        )

    return QueryResponse(
        results=query_results,
        total_matched=total,
        extracted_filters=filters if parsed is not None else None,
        extracted_profile=profile,
    )
```

Modify `src/daad_search/api/main.py`: add the import and the new route.

```python
from ..query_understanding.schema import QueryRequest, QueryResponse
from .query import handle_query
```

```python
@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest, session: AsyncSession = Depends(get_session)
) -> QueryResponse:
    return await handle_query(session, request.query, request.limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_query_api.py -v -m integration`
Expected: PASS (3 passed). These use mocked `parse_query`/`reason_about_eligibility` (via monkeypatch) so they don't make real LLM calls, but do need live Postgres (+ Qdrant for the parse-failure-fallback test).

Then run the full suite once to confirm nothing regressed: `.venv/bin/python -m pytest -v -m "not integration"` and `.venv/bin/python -m pytest -v -m integration`.

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/query_understanding/schema.py src/daad_search/api/query.py src/daad_search/api/main.py tests/test_query_api.py
git commit -m "feat: query understanding orchestration and POST /query endpoint"
```

---

## Final Verification

After Task 5, run the whole suite:

```bash
.venv/bin/python -m pytest -v -m "not integration"   # fast unit tests, no services needed
.venv/bin/python -m pytest -v -m integration          # requires: docker compose up -d, .env with GROQ/MISTRAL/GEMINI keys
```

Then try a real end-to-end query (make sure the catalog has at least one program with extracted eligibility data — `python -m daad_search.cli extract --ids 10396` if not):

```bash
uvicorn daad_search.api.main:app --reload &
curl -X POST localhost:8000/query -H "content-type: application/json" \
  -d '{"query": "I have a bachelors in AI from Pakistan with CGPA 3.2, want English-taught no-fee masters in Germany focused on machine learning"}'
```

Inspect the response: `extracted_filters`/`extracted_profile` should reflect what was actually said in the query, and any result with extracted eligibility data should carry a non-`no_data` verdict with a specific, cited `eligibility_reasoning`.

At this point the query-understanding spec is fully implemented: a single `/query` call turns a free-text search into ranked, eligibility-annotated results, ready for the frontend spec to build a UI around.
