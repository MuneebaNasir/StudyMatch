# Data Foundation & Hybrid Retrieval — Design

## Context

This is the first sub-project of a larger portfolio application: a web app where international students describe their academic background and preferences in natural language, and get back German study programs they're eligible for, with an admission guide. The app is being built as an ML Engineer (LLM Domain) portfolio piece targeting the German tech market.

The overall system decomposes into independent specs:

1. **This spec** — data foundation: ingest program data from DAAD into Postgres + Qdrant, expose a hybrid search API.
2. **Eligibility extraction** (next) — LLM pipeline that parses each program's raw admission-requirements text into structured fields (min CGPA, accepted bachelor's subjects, language test thresholds, GRE/GMAT requirements).
3. **Query understanding** — LLM turns a free-text user query into structured filters + a semantic query, calls this spec's search API, and reasons over each candidate's structured eligibility (from spec 2) against the user's stated profile to produce a per-program eligibility verdict.
4. **Frontend** — chat-style query input, results with eligibility verdicts, and an admission-guide panel per program.

This document covers spec 1 only.

## Goal

Build a repeatable ingestion pipeline that pulls study program data from DAAD's International Programmes catalog, stores it in Postgres (structured, filterable fields) and Qdrant (semantic embeddings), and exposes a hybrid search API combining hard filters with semantic similarity. This API is what spec 3's query-understanding layer will call.

## Data Source

DAAD (Deutscher Akademischer Austauschdienst) runs a public search interface for study programs at `www2.daad.de/deutschland/studienangebote/international-programmes/`. The site has no documented public API, but its own frontend calls an **undocumented Solr-backed JSON API**, discovered by inspecting the site's JS bundle:

- `GET .../international-programmes/api/solr/en/search.json` — paginated list of program summaries, supports filters (`degree[]`, `fos`, `subjectGroup[]`, etc.)
- `GET .../international-programmes/api/solr/en/count.json` — result counts and facets, same filter params
- `GET .../international-programmes/api/solr/en/map.json` — geo-grouped results (not used)
- `GET .../international-programmes/api/solr/en/suggest.json` — autosuggest (not used)

`count.json` with no filters reports **2,418 total programs** across all degree types (1,718 master's, 350 bachelor's, 145 PhD, plus graduate school / language / short / preparatory courses).

Each program's detail page (`.../en/detail/{id}/`, server-rendered HTML) contains DAAD's own aggregated write-up in consistently labeled sections: *Description/content*, *Academic admission requirements*, *German language skills*, *English language skills*, GRE/GMAT requirements, costs, and application deadlines. This text is not available via the JSON API and must be scraped per-program.

**Legality/etiquette:** `www2.daad.de` has no `robots.txt` restricting these paths; `ip.daad.de`'s `robots.txt` explicitly allows all crawling. This is an unofficial API, so regardless of robots.txt the pipeline self-imposes rate limiting, a descriptive User-Agent, and response caching to avoid hammering DAAD's infrastructure. This project consumes publicly listed data non-commercially and always links back to the canonical DAAD detail page as the source of truth — it does not redistribute or resell the dataset.

## Scope

**In scope:**
- Scraping all ~2,418 programs across every degree type (not just master's) — marginal cost is near-zero since it's the same paginated JSON endpoint
- Scraping each program's detail page for raw eligibility/admission text, stored verbatim (not yet structured — that's spec 2)
- Postgres schema + idempotent upsert logic (re-runnable without duplicating)
- Voyage AI embeddings on title + subject + description, indexed in Qdrant
- A FastAPI hybrid search endpoint: Postgres hard filters intersected/re-ranked with Qdrant semantic similarity
- Docker Compose for local Postgres + Qdrant
- A manual CLI command to (re-)run the full ingestion

**Explicitly out of scope:**
- Parsing raw eligibility text into structured fields (spec 2)
- Natural-language query understanding (spec 3)
- Any frontend (spec 4)
- Scheduled/automatic refresh — manual re-run only for now; automation can be added later without changing the pipeline's design

## Architecture

```
1. List fetch (search.json, paginated, all degree types)
        |
        v
2. Detail fetch (per-program HTML -> raw text sections)
        |
        v
3. Upsert Postgres (structured columns + raw_sections jsonb)
        |
        v
4. Embed + upsert Qdrant (Voyage AI on title+subject+description)
        |
        v
5. FastAPI hybrid search endpoint
```

**Stage 1 — List fetch:** Page through `search.json` with no degree filter, collecting all program summaries: `id, courseName, courseNameShort, academy (university), city, languages, courseType, programmeDuration, beginning, tuitionFees, subject, link`. This is the source of truth for which program IDs exist.

**Stage 2 — Detail fetch:** For each ID, fetch the detail page and extract the labeled text sections by their DAAD headings. Stored verbatim. Kept deliberately "dumb" (no normalization) since this HTML structure is unofficial and could drift — spec 2 owns turning this into structured, validated fields.

**Stage 3 — Postgres upsert:** DAAD's numeric `id` is the primary key; re-running the pipeline updates existing rows rather than duplicating.

**Stage 4 — Embedding:** One embedding per program from `courseName + subject + description text`, via Voyage AI, upserted into Qdrant keyed by the same program ID.

**Stage 5 — Hybrid search API:** Hard filters run as a Postgres query to get a candidate ID set; if a semantic query is present, Qdrant is queried restricted to that candidate set (via payload filter) and results ranked by similarity; otherwise Postgres results are returned as-is.

**Resilience (stages 1–2):** rate-limited/concurrency-capped requests, descriptive User-Agent, on-disk response caching so re-runs don't re-hit DAAD for unchanged pages, per-ID failure isolation (a failed detail fetch is logged and retried/skipped, never aborts the run).

## Data Model

### Postgres — `programs` table

| Column | Type | Notes |
|---|---|---|
| `id` | `integer` PK | DAAD's own program ID — stable across re-scrapes |
| `course_name` | `text` | |
| `course_name_short` | `text` | |
| `university` | `text` | DAAD's `academy` field |
| `city` | `text` | |
| `languages` | `text[]` | e.g. `{English}`, `{English,German}` |
| `subject` | `text` | DAAD's subject label; used for filtering and embedding |
| `course_type` | `integer` | DAAD's degree code: 1=Bachelor's, 2=Master's, 3=PhD, 4=Graduate school, 5=Language course, 6=Short course, 7=Preparatory course, 9=Various |
| `degree` | `text` | human-readable degree name from detail page, e.g. "Master of Science" |
| `duration` | `text` | e.g. "4 semesters" |
| `beginning` | `text` | e.g. "Winter and summer semester" |
| `tuition_fees_text` | `text` | raw string |
| `has_tuition_fees` | `boolean` | derived, for the common "no fees" filter |
| `application_deadline_text` | `text` | raw string — too varied to normalize safely without spec 2 |
| `link` | `text` | canonical DAAD detail page URL, always shown to the user as source of truth |
| `raw_sections` | `jsonb` | `{admission_requirements, german_language, english_language, description, costs}` — verbatim detail-page text, spec 2's input |
| `scraped_at` | `timestamptz` | last successful scrape time for this row |

Indexes: `subject`, `languages` (GIN), `has_tuition_fees`, `course_type`, `city`.

### Qdrant — `programs` collection

- Vector: Voyage AI embedding of `f"{course_name}. {subject}. {description}"`
- Payload: `{program_id, subject, languages, has_tuition_fees, course_type}`
- Point ID = Postgres `id`

## API Contract

`POST /search`

```jsonc
// Request
{
  "filters": {
    "languages": ["English"],
    "max_tuition_free_only": true,
    "subject": "Computer Science",
    "city": "Berlin",
    "course_type": 2
  },
  "semantic_query": "machine learning and robotics",
  "limit": 20
}

// Response
{
  "results": [
    {
      "id": 10396,
      "course_name": "Additive Manufacturing",
      "university": "Paderborn University",
      "city": "Paderborn",
      "languages": ["English"],
      "subject": "Mechanical Engineering",
      "tuition_fees_text": "No tuition fees",
      "application_deadline_text": "This programme has no deadline listed.",
      "link": "https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/10396/",
      "score": 0.83
    }
  ],
  "total_matched": 47
}
```

Also: `GET /programs/{id}` returning the full row including `raw_sections` (used by spec 2 and by the frontend's admission-guide view).

**Behavior:**
- No filters + no semantic query → plain paginated listing.
- Filters only → pure Postgres query, no Qdrant call.
- Semantic query only → Qdrant search over the full collection.
- Both → Postgres narrows candidates, Qdrant ranks within that set.

## Error Handling

- Detail-page fetch failure (network error, 404, unexpected HTML) → log with program ID, leave existing row untouched, add to a `failed_ids` retry list surfaced at end of run.
- HTML structure drift → section parser returns `None` per missing section rather than throwing; a per-run summary of "sections not found" is logged so drift is visible immediately.
- Voyage AI / Qdrant failure → retried with backoff; a program without an embedding is excluded from semantic search but remains usable via hard-filter-only search until the next run.

## Testing

- Unit tests for the `search.json` list parser and detail-page section parser, against saved HTML/JSON fixtures (not live requests).
- Integration test: run the pipeline against a handful of fixed real program IDs, assert correct Postgres rows and Qdrant points.
- API tests for `/search`: filters-only, semantic-only, combined, empty-result, pagination.

## Tech Stack

- Python + FastAPI for the search API
- SQLAlchemy/asyncpg for Postgres
- `qdrant-client` for Qdrant
- `httpx` for scraping
- Voyage AI for embeddings
- Docker Compose for local Postgres + Qdrant
