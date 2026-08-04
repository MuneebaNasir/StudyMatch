# Eligibility Extraction — Design

## Context

This is the second sub-project of a larger portfolio application: a web app where international students describe their academic background and preferences in natural language, and get back German study programs they're eligible for, with an admission guide. The app is being built as an ML Engineer (LLM Domain) portfolio piece targeting the German tech market.

The overall system decomposes into independent specs:

1. **Data foundation** (done) — ingest program data from DAAD into Postgres + Qdrant, expose a hybrid search API.
2. **This spec** — eligibility extraction: LLM pipeline that parses each program's raw admission-requirements text (scraped in spec 1) into structured, queryable fields.
3. **Query understanding** (next) — LLM turns a free-text user query into structured filters + a semantic query, calls spec 1's search API, and reasons over each candidate's structured eligibility (from this spec) against the user's stated profile to produce a per-program eligibility verdict.
4. **Frontend** — chat-style query input, results with eligibility verdicts, and an admission-guide panel per program.
5. **Prerequisite/transcript matching** (parked, future) — German universities publish per-university regulatory documents (*Zulassungsordnung*/*Studienordnung*) listing specific prerequisite coursework, separate from DAAD's own admission text. A future spec could let a user upload their transcript and match it against a program's actual regulatory document. This is a substantially different data-acquisition problem (per-university, often German-language PDFs, no centralized index) from what this spec covers, so it's tracked here as a roadmap item, not built now.

This document covers spec 2 only.

## Goal

Build a repeatable extraction pipeline that reads each program's raw `admission_requirements`, `german_language`, and `english_language` text (already in Postgres from spec 1) and uses an LLM to produce structured, queryable eligibility fields — including conditional rules (e.g. "GRE waived if CGPA ≤ 1.3") and a verbatim source citation per extracted claim, for the eventual admission-guide view. This is spec 3's primary input for reasoning about whether a specific student is eligible for a specific program.

## Scope

**In scope:**
- Structured extraction from DAAD's own already-scraped text only (no new scraping/data source)
- A schema capturing: degree prerequisite, minimum grade requirement (as DAAD states it, no cross-grading-scale conversion), GRE/GMAT requirement with subscores and waiver conditions, German and English language requirements with accepted-test alternatives
- A new `eligibility` Postgres table, 1:1 with `programs`
- Idempotent, auto-resumable extraction — a re-run only processes programs still missing an eligibility row, no manual ID tracking required
- A CLI command (`extract`) mirroring the existing `ingest` command
- LangChain + Groq (`llama-3.3-70b-versatile`, free tier) for the extraction call itself

**Explicitly out of scope:**
- Per-university regulatory/prerequisite document fetching and transcript matching (parked as spec 5, see Context)
- Grade-scale conversion or eligibility reasoning against an actual student profile — that's spec 3's job; this spec only extracts what DAAD's text states, verbatim in meaning
- Any UI for this data (spec 4)
- Scheduled/automatic re-extraction — manual `extract` re-run only, same as spec 1's `ingest`

## Data Source

No new data source. Input is `programs.raw_sections` (JSONB, from spec 1), specifically the `admission_requirements`, `german_language`, and `english_language` keys when present. A confirmed 24 programs in the current catalog have *none* of these three keys (a different DAAD page template entirely — see spec 1's finding that ~7% of the catalog, concentrated in non-degree course types 4/5/6/7/56, lacks `admission_requirements`). Candidate selection excludes these: there is nothing to extract, so calling the LLM on them would only burn a free-tier request for a guaranteed-empty result. They're left with no `eligibility` row, same as any other program not yet processed — spec 3 treats a missing row as "no extracted eligibility data," not as a false "no requirements."

## Extraction Schema

Validated live against 3 real, structurally different programs (a complex conditional-GRE-waiver case, a plain CGPA-only case, and a minimal one-line case) before being finalized. Two iterations were needed to fix real problems the live test surfaced: language-test alternatives were initially being marked as separately mandatory (risk of wrongly rejecting an applicant who only has one of several accepted certificates), and language-test score thresholds were leaking into the field meant only for GRE/GMAT.

```python
class SubScore(BaseModel):
    section: str
    min_score: float


class StandardizedTest(BaseModel):
    """GRE or GMAT only — language tests go under LanguageRequirement instead."""
    test: str                               # "GRE" or "GMAT"
    required: bool
    eligibility_condition: str | None       # WHO/WHEN this applies (e.g. nationality-based)
    subscores: list[SubScore]
    waiver: str | None
    source_quote: str


class AcceptedTest(BaseModel):
    """One way to satisfy a language requirement, e.g. IELTS 6.5."""
    test_name: str
    min_score: str                          # string: formats vary ("6.5", "72", "B2 First")


class LanguageRequirement(BaseModel):
    language: str                           # "German" or "English"
    level: str                              # CEFR code, or "none_required"
    accepted_tests: list[AcceptedTest]       # ANY ONE satisfies — not all separately required
    source_quote: str


class GradeRequirement(BaseModel):
    value: float | None
    scale: str | None                       # e.g. "German grading scale (1.0 best – 5.0 worst)"
    source_quote: str | None


class DegreePrerequisite(BaseModel):
    description: str
    source_quote: str


class EligibilityExtraction(BaseModel):
    requires_gre: bool | None
    requires_gmat: bool | None
    min_german_level: str | None
    min_english_level: str | None
    extraction_confidence: Literal["high", "medium", "low"]
    degree_prerequisite: DegreePrerequisite | None
    grade_requirement: GradeRequirement | None
    standardized_tests: list[StandardizedTest]
    language_requirements: list[LanguageRequirement]
    notes: str | None                       # catch-all for real but unmapped requirements
                                             # (e.g. a country-specific APS certificate)
```

**Every claim carries a `source_quote`** — a self-contained excerpt (full sentence/list block, not an isolated fragment) copied verbatim from `raw_sections`, so the eventual admission-guide UI can show *why* behind each field, not just a bare value.

**Extraction prompt** combines `admission_requirements` + `german_language` + `english_language` for one program into a single call, with explicit instructions (validated to matter — removing them measurably degraded output) that:
- `standardized_tests` is GRE/GMAT only; language proficiency tests never belong there
- accepted language tests listed together are *alternatives* (any one suffices), never separately mandatory
- `eligibility_condition` means who/when a test applies, not its score thresholds
- `source_quote` must be a full, self-contained excerpt

## Architecture

```
1. Select candidates (programs with no eligibility row yet)
        |
        v
2. Per program: build prompt from raw_sections
        |
        v
3. LLM call (Groq llama-3.3-70b-versatile via LangChain structured output)
        |
        v
4. Validate against EligibilityExtraction schema
        |
        v
5. Upsert into `eligibility` table (scalar columns + full JSONB)
```

### Postgres — `eligibility` table

New table, not new columns on `programs` (no migration tool yet; `init_db()`'s `create_all()` creates new tables without touching existing populated ones).

| Column | Type | Notes |
|---|---|---|
| `program_id` | `integer` PK, FK → `programs.id` | 1:1 with `programs` |
| `requires_gre` | `boolean`, nullable | null = not stated/unclear |
| `requires_gmat` | `boolean`, nullable | |
| `min_german_level` | `text`, nullable | CEFR code, or `"none_required"` |
| `min_english_level` | `text`, nullable | CEFR code, or `"none_required"` |
| `min_grade_value` | `float`, nullable | as literally stated, no scale conversion |
| `min_grade_scale_note` | `text`, nullable | e.g. "German grading scale (1.0 best – 5.0 worst)" |
| `extraction_confidence` | `text` | `"high"` / `"medium"` / `"low"`, LLM self-assessed |
| `structured_eligibility` | `jsonb` | full `EligibilityExtraction` dump, incl. citations |
| `extracted_at` | `timestamptz` | |

Indexes: `requires_gre`, `requires_gmat`, `min_german_level`, `min_english_level` (spec 3's expected filter columns).

### Module layout

Mirrors the `ingestion/` package from spec 1:
- `src/daad_search/extraction/__init__.py` (empty)
- `src/daad_search/extraction/schema.py` — the Pydantic models above
- `src/daad_search/extraction/extractor.py` — prompt building, `get_extraction_llm()` singleton (`ChatGroq(model="llama-3.3-70b-versatile", max_retries=3)`), `extract_eligibility(course_name, university, raw_sections) -> EligibilityExtraction`
- `src/daad_search/extraction/pipeline.py` — `run_extraction(limit_ids=None, limit=None) -> dict`
- `db/upsert.py` gains `upsert_eligibility(session, program_id, values)`, same `ON CONFLICT DO UPDATE` idempotent pattern as `upsert_program`

### CLI

```bash
python -m daad_search.cli extract              # everything still missing extraction
python -m daad_search.cli extract --limit 900   # cap this run's size (e.g. to respect a daily quota)
python -m daad_search.cli extract --ids 10396   # targeted re-extraction
```

`run_extraction` selects candidates via `programs LEFT JOIN eligibility ... WHERE eligibility.program_id IS NULL AND (raw_sections ? 'admission_requirements' OR raw_sections ? 'german_language' OR raw_sections ? 'english_language')` (plus the `--ids`/`--limit` narrowing) — no manual bookkeeping of what's already done, and programs with no relevant text are never sent to the LLM. Re-running the bare `extract` command after a quota cutoff automatically resumes.

## Error Handling

- **Per-program failure isolation:** fetch → prompt → LLM call → validate → upsert is wrapped per program; one failure never aborts the run, matching `ingest_program`'s pattern from spec 1.
- **LLM call failure** (transient network/API error): `ChatGroq`'s `max_retries=3` handles it; if still failing, log and leave the program without an eligibility row for the next run.
- **Schema validation failure** (LLM output doesn't parse into `EligibilityExtraction` — occasional on open-weight models): caught, logged with the raw response for debugging, counted as failed, skipped.
- **Consecutive-failure circuit breaker:** 5 failures in a row (a strong signal of quota exhaustion, not per-program bad luck) stops the run early with a clear log message, rather than looping through the remaining catalog making doomed calls.
- Run summary: `{"total_candidates", "succeeded", "failed_ids", "stopped_early": bool}`, printed by the CLI same as `ingest`.

## Testing

- Unit tests: `EligibilityExtraction` schema validation (valid/invalid payloads); prompt-building as a pure function, no LLM call.
- Integration tests (`pytest.mark.integration`, require `GROQ_API_KEY` + live Postgres):
  - `extract_eligibility()` against fixed real admission-text fixtures (the 3 programs validated during design — conditional GRE waiver, plain CGPA case, minimal text) asserting the specific behaviors confirmed live: GRE waiver captured, alternative language tests grouped (not separately required), grade threshold captured
  - `run_extraction()` end-to-end against a couple of real program IDs in the test DB, asserting `eligibility` rows land correctly
  - Idempotency: running `extract` twice only processes each program once
  - Circuit breaker: a mocked always-failing LLM triggers early stop after 5 failures, not a full catalog loop

## Tech Stack

- LangChain (`langchain-groq`) for the extraction LLM call and structured output
- Groq API, `llama-3.3-70b-versatile` (free tier)
- SQLAlchemy/asyncpg for the new `eligibility` table (same engine/session as spec 1)
- Pydantic for the extraction schema
