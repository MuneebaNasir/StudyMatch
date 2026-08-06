# Query Understanding — Design

## Context

This is the third sub-project of a larger portfolio application: a web app where international students describe their academic background and preferences in natural language, and get back German study programs they're eligible for, with an admission guide. The app is being built as an ML Engineer (LLM Domain) portfolio piece targeting the German tech market.

The overall system decomposes into independent specs:

1. **Data foundation** (done) — ingest program data from DAAD into Postgres + Qdrant, expose a hybrid search API.
2. **Eligibility extraction** (done) — LLM pipeline that parses each program's raw admission-requirements text into structured, queryable fields.
3. **This spec** — query understanding: LLM turns a free-text query into structured filters + a semantic query + the student's own profile, calls spec 1's search, and reasons over each candidate's structured eligibility (spec 2) against the student's profile to produce a per-program eligibility verdict.
4. **Frontend** (next) — chat-style query input, results with eligibility verdicts, and an admission-guide panel per program.
5. **Prerequisite/transcript matching** (parked, future) — matching an uploaded transcript against a university's actual regulatory document, separate from DAAD's own admission text.
6. **Deployment** (parked, future) — as built, the whole stack runs locally (Docker Compose + `uvicorn` on a developer's machine). Making the site publicly available without depending on any one machine being on is a real, separate design question (hosting, managed Postgres/Qdrant, cost) — noted here as a roadmap item, not addressed by this spec. This spec's LLM-provider design (see below) is deliberately deployment-agnostic so it isn't blocked on that decision.

This document covers spec 3 only.

## Goal

A new `POST /query` FastAPI endpoint that takes one free-text query and, in a single request: parses it into search filters + a semantic query + the student's academic profile, runs the existing hybrid search in-process, and returns the matched programs annotated with a per-program eligibility verdict reasoned from each program's structured eligibility data (spec 2) against the student's stated profile.

## Scope

**In scope:**
- Free-text → `{filters, semantic_query, student_profile}` extraction (one LLM call)
- Batched eligibility reasoning over the top 10 search results (one LLM call per query, not per candidate)
- Grade-scale comparison (e.g. a US-style 4.0 GPA against a German-scale threshold) done by LLM judgment, not a hand-coded conversion formula
- A 3-tier automatic LLM provider fallback chain (Groq → Mistral → Gemini, all free tiers) plus application-level graceful degradation if all three fail
- Graceful handling of candidates with no `Eligibility` row yet (most of the catalog currently, since extraction has only run against a handful of programs so far)

**Explicitly out of scope:**
- Any frontend (spec 4)
- The prerequisite/transcript-matching idea (parked, spec 5)
- Deployment/hosting (parked, spec 6)
- Persisting past queries/conversation history — stateless per-request for now
- Fixing the known `requires_gre`/`requires_gmat` flakiness from spec 2 — this spec reads the reliable nested `structured_eligibility` detail directly, which is exactly the workaround that limitation already calls for
- OpenAI as an automatic fallback tier — available via explicit manual config only, since it's not free and silently falling through to it on a busy day would incur real charges without the operator choosing to

## LLM Provider Strategy

Query understanding runs on every live user request (unlike spec 2's one-time batch extraction), so quota exhaustion on any single free provider is a real availability risk, not just a slow-down. Two layers of resilience:

**Layer 1 — automatic provider fallback**, via LangChain's `.with_fallbacks()`: each of the two LLM calls (parse, reason) is built against a chain of **Groq (`llama-3.3-70b-versatile`) → Mistral (free tier) → Gemini (`gemini-2.0-flash`, free tier)**. If the primary provider fails (rate limit, network error, malformed output after its own retries), LangChain transparently tries the next provider in the chain with the same prompt/schema — the caller never sees the individual provider failure unless all three are exhausted. All three are genuinely free, no credit card required.

**Layer 2 — application-level graceful degradation**, if all three providers fail:
- Query-parse failure → fall back to a pure semantic search (raw query text as `semantic_query`, no filters, no profile) rather than a hard error — the user still gets ranked results. `extracted_filters`/`extracted_profile` come back `null`.
- Eligibility-reasoning failure → the search already succeeded by this point; return results with `eligibility_verdict: "unclear"` for the candidates that would have been reasoned about, rather than discarding the search results.

**OpenAI** is available (a key exists) but deliberately excluded from the automatic chain — wiring it in without an explicit opt-in risks silently incurring real charges the moment both free tiers are exhausted during, say, a demo. It's a manual config override, not a default.

This whole design is deployment-agnostic by construction: all three fallback tiers are hosted APIs, not anything running on the developer's own machine, so the same code works identically whether it's running locally or eventually deployed (spec 6, parked) — a laptop-local model was considered and rejected for exactly this reason.

## Extraction Schemas

**Call 1 — parse the free-text query** into filters + semantic query + student profile. Reuses the existing `SearchFilters` schema from spec 1 directly:

```python
class StudentProfile(BaseModel):
    degree_field: str | None = None        # e.g. "Artificial Intelligence"
    grade_value: float | None = None        # as stated, e.g. 3.2
    grade_scale: str | None = None          # as stated, e.g. "4.0 GPA scale (USA)"
    nationality: str | None = None          # relevant for EU/EEA-gated waivers (spec 2's GRE example)
    other_notes: str | None = None          # catch-all, e.g. "3 years work experience"


class ParsedQuery(BaseModel):
    filters: SearchFilters                  # reused from daad_search.api.schemas
    semantic_query: str | None = None       # the substantive, non-filter/non-profile part
    student_profile: StudentProfile
```

**Call 2 — batched eligibility reasoning** over the (up to 10) candidates that have extracted eligibility data:

```python
class EligibilityVerdict(BaseModel):
    program_id: int
    verdict: Literal["eligible", "likely_eligible", "not_eligible", "unclear"]
    reasoning: str                          # short explanation, cites the specific criteria that drove the verdict


class BatchEligibilityReasoning(BaseModel):
    verdicts: list[EligibilityVerdict]
```

`"no_data"` is not an LLM-producible value — candidates with no `Eligibility` row are filtered out before the LLM call and assigned `"no_data"` deterministically by the orchestration code, the same "never send the LLM something it structurally can't reason about" pattern spec 2 already established.

## Architecture

```
1. Parse query (LLM call 1: free text -> ParsedQuery)
        |
        v
2. Search (reuse spec 1's filtered_search/hybrid_search in-process, not HTTP)
        |
        v
3. Split the first min(10, limit) results (by rank — the request's own `limit`
   still governs how many results come back to the client overall, but
   eligibility reasoning is capped at 10 regardless of how high `limit` is
   set, and scales down if `limit` itself is below 10): has eligibility data
   vs. no data yet
        |
        v
4. Batch eligibility reasoning (LLM call 2: student_profile + each candidate's
   structured_eligibility -> verdicts), only for the has-data subset
        |
        v
5. Merge verdicts back into results (no-data candidates get "no_data"
   deterministically), return combined response
```

### `POST /query`

`limit` mirrors `/search`'s own field exactly (spec 1): `limit: int = Field(20, ge=1, le=100)`. Omitting it defaults to 20, never unbounded; `<1` or `>100` is rejected with a 422, same as `/search`. Eligibility reasoning is separately capped at `min(10, limit)` regardless — with the default `limit=20`, the first 10 (by rank) get a verdict and the remaining 10 are real search matches too, just past the reasoning cutoff. Every result carries an `eligibility_verdict`; `"no_data"` covers both "past the top-10 reasoning cutoff" and "within it but lacking an `Eligibility` row" — the frontend doesn't need to distinguish the two, both mean "no verdict available for this one."

```jsonc
// Request
{ "query": "bachelors in AI from Pakistan, CGPA 3.2, English-taught no-fee masters in ML", "limit": 20 }

// Response
{
  "results": [
    {
      "id": 10396, "course_name": "...", "university": "...", "city": "...",
      "languages": ["English"], "subject": "...", "tuition_fees_text": "...",
      "application_deadline_text": "...", "link": "...", "score": 0.83,
      "eligibility_verdict": "eligible",
      "eligibility_reasoning": "Your 3.2/4.0 GPA converts to roughly 2.0 on the German scale, comfortably under the 2.5 maximum required..."
    },
    { "id": 55555, "...": "...", "eligibility_verdict": "no_data", "eligibility_reasoning": null }
  ],
  "total_matched": 47,
  "extracted_filters": { "languages": ["English"], "max_tuition_free_only": true },
  "extracted_profile": { "degree_field": "Artificial Intelligence", "grade_value": 3.2, "grade_scale": "4.0 GPA (USA)", "nationality": "Pakistan" }
}
```

`extracted_filters`/`extracted_profile` are returned for transparency/debuggability — exactly what spec 4's frontend will want to show the user as "here's what we understood from your query," letting them correct a bad extraction. Both come back `null` if Layer 2's parse-failure fallback engaged.

### Module layout

New package mirroring `extraction/`:
- `src/daad_search/query_understanding/schema.py` — the two schemas above
- `src/daad_search/query_understanding/llm.py` — builds the shared Groq→Mistral→Gemini fallback chain (one per schema, since `.with_structured_output()` is applied per-provider before composing fallbacks)
- `src/daad_search/query_understanding/parser.py` — `parse_query(query: str) -> ParsedQuery | None` (`None` signals Layer 2 fallback should engage)
- `src/daad_search/query_understanding/reasoner.py` — `reason_about_eligibility(profile: StudentProfile, candidates: list[tuple[SearchResult, Eligibility]]) -> list[EligibilityVerdict] | None`
- `src/daad_search/api/query.py` — orchestration: `handle_query(session, query, limit) -> QueryResponse`, wiring steps 1-5, following the same split as `api/search.py` (logic) vs `api/main.py` (route registration)
- `api/schemas.py` gains `QueryRequest`, `QueryResult` (`SearchResult` + verdict fields), `QueryResponse`
- `api/main.py` gains the `POST /query` route

### Config additions

`mistral_api_key`, `gemini_api_key` alongside the existing `groq_api_key` in `Settings`. `openai_api_key` also present (for the manual-override path) but never read by the automatic chain.

## Error Handling

- **Per-call resilience** is the 2-layer design above (provider fallback, then graceful degradation) — this replaces a simple retry-then-fail approach since the endpoint is live and synchronous, not a resumable batch job like spec 2.
- **Verdict/candidate mismatch:** the LLM's batch response is matched back to candidates by `program_id`. Any candidate the response doesn't cover (omitted, or a hallucinated ID that doesn't match anything sent) falls back to `"unclear"` — never silently dropped from the results list.
- **No magic bullet for total quota exhaustion:** if all three providers are genuinely exhausted at once (unlikely, but possible under sustained heavy use), Layer 2's degradation still applies — search always works, eligibility reasoning becomes `"unclear"`. This is a known operational ceiling of relying on free tiers, same acknowledgment as spec 2.

## Testing

- **Unit tests:** schema validation (`ParsedQuery`, `StudentProfile`, `EligibilityVerdict`, `BatchEligibilityReasoning`); the candidate has-data/no-data split as a pure function; the verdict-merge-by-`program_id` logic (including the mismatch/omission case) as a pure function — all testable with hand-built data, no LLM/DB.
- **Integration tests** (`pytest.mark.integration`, live Postgres/Qdrant + at least Groq):
  - `parse_query()` against the original product example query, asserting filters + profile extracted correctly
  - `reason_about_eligibility()` against real extracted eligibility data (program 10396) with two crafted profiles — one clearly eligible, one clearly over-threshold — asserting sensible verdicts
  - Full `POST /query` end-to-end via `TestClient`
  - Both Layer 2 degradation paths: a monkeypatched failing `parse_query` still returns ranked results; a monkeypatched failing `reason_about_eligibility` still returns search results with `"unclear"` verdicts
  - Layer 1 fallback: at minimum a unit-level test (mocked providers) confirming the chain actually falls through to the 2nd/3rd provider when the 1st raises — live-testing genuine multi-provider failover isn't practical without deliberately breaking a working provider

## Tech Stack

- LangChain (`langchain-groq`, `langchain-mistralai`, `langchain-google-genai`) with `.with_fallbacks()` for provider resilience
- Groq `llama-3.3-70b-versatile`, Mistral free-tier model, Gemini `gemini-2.0-flash` — all free
- Reuses spec 1's FastAPI/SQLAlchemy stack and search logic (`filtered_search`/`hybrid_search`) directly, in-process
- Reuses spec 2's `Eligibility` table and `structured_eligibility` data
