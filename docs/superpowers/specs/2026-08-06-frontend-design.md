# Frontend — Design

## Context

This is the fourth sub-project of a larger portfolio application: a web app where international students describe their academic background and preferences in natural language, and get back German study programs they're eligible for, with an admission guide. The app is being built as an ML Engineer (LLM Domain) portfolio piece targeting the German tech market.

The overall system decomposes into independent specs:

1. **Data foundation** (done) — ingest program data from DAAD into Postgres + Qdrant, expose a hybrid search API.
2. **Eligibility extraction** (done) — LLM pipeline that parses each program's raw admission-requirements text into structured, queryable fields.
3. **Query understanding** (done) — `POST /query` turns a free-text query into structured filters + a semantic query + the student's own profile, and reasons over each candidate's structured eligibility against that profile to produce a per-program eligibility verdict.
4. **This spec** — a React frontend: a chat-style query box, results annotated with eligibility verdicts, an editable summary of what the backend understood from the query, and a structured admission-guide panel per program.
5. **Prerequisite/transcript matching** (parked, future) — matching an uploaded transcript against a university's actual regulatory document, separate from DAAD's own admission text.
6. **Deployment** (parked, future) — as built, the whole stack runs locally (Docker Compose + `uvicorn` + a Vite dev server on a developer's machine). Making the site publicly available is a separate, later design question; this spec's frontend has no deployment-specific concerns baked in that would block it.

This document covers spec 4 only.

## Goal

A React + TypeScript single-page app, served by Vite's dev server, that lets a user type a free-text description of their background and what they're looking for, see ranked results annotated with a per-program eligibility verdict, correct the backend's extracted understanding of their query without waiting on the LLM again, and open a structured admission-guide panel per program showing exactly which requirement text drove each part of the verdict.

## Scope

**In scope:**
- A chat-styled single-shot query box (not a multi-turn conversation — `/query` is stateless per request; each submission is independent)
- An editable summary of `extracted_filters`/`extracted_profile` as removable/editable chips, where edits re-run `/search` directly (bypassing the LLM parse) for instant correction
- A results list with a color-coded eligibility verdict badge and reasoning excerpt per program
- A side-panel/drawer admission guide per program: verdict + reasoning, then a structured breakdown (grade requirement, language requirements, standardized tests, degree prerequisite) each with its supporting `source_quote`, falling back to raw admission text when no structured extraction exists yet
- Loading, error, and empty-result states throughout
- A small, additive backend touch: CORS middleware, and a `structured_eligibility` field added to `ProgramDetail`

**Explicitly out of scope:**
- True multi-turn conversation / conversation history (the backend has no memory; adding one is a separate, larger design decision not needed for v1)
- User accounts, authentication, saved/bookmarked programs
- A traditional persistent faceted-filter sidebar as the primary filter UI — filtering happens through the query box and the extracted chips, not a separate always-on control panel
- Deployment/hosting (parked, spec 6)
- The prerequisite/transcript-matching idea (parked, spec 5)
- End-to-end (browser-driven) tests — component-level tests are the bar for v1

## Interaction Model

One free-text box, styled like a chat composer, submits once per query — there is no running conversation thread and no server-side memory across submissions. This matches `/query`'s actual contract exactly instead of building conversational UI atop a stateless endpoint. If a user wants to change their query, they either edit the extracted chips (instant, client-side re-filter) or rephrase and resubmit (a fresh `/query` call, including fresh eligibility reasoning).

## Architecture

New top-level `frontend/` directory, sibling to `src/`, with its own `package.json` — independent of the Python backend's build/deploy lifecycle.

```
frontend/
  src/
    api/          # typed fetch wrappers: postQuery, postSearch, getProgram — one file, mirrors backend schemas
    components/
      ChatQueryBox.tsx
      ExtractionSummary.tsx      # editable chips
      ResultsList.tsx / ResultCard.tsx
      AdmissionGuideDrawer.tsx
    hooks/
      useQuerySearch.ts          # wraps /query via TanStack Query
      useFilteredSearch.ts       # wraps /search, used on chip edits
      useProgramDetail.ts        # wraps GET /programs/{id}, used on drawer open
    types.ts      # TS mirrors of the Pydantic schemas (SearchFilters, StudentProfile, QueryResult, ProgramDetail, ...)
    App.tsx
  vite.config.ts
  package.json
```

**Stack:** React + Vite + TypeScript; Tailwind CSS + shadcn/ui for styling and accessible primitives (drawer, badge, skeleton) that are owned/customized rather than imported as an opaque library; TanStack Query for all server-data fetching (caching, loading/error state, avoids hand-rolled race-condition bookkeeping at each of the three call sites); plain `useState`/`useReducer` for UI-only state (drawer open/closed, selected program id, edited filter state) — the app has no cross-cutting client state complex enough to justify a global-state library.

**Backend touch (small, additive, in `src/daad_search/api/`):**
1. `main.py` gains `CORSMiddleware`, allowing the Vite dev origin — nothing currently permits a browser on a different port to call the API.
2. `ProgramDetail` (in `api/schemas.py`) gains `structured_eligibility: dict | None`, populated in `GET /programs/{id}` via a `LEFT JOIN` against `Eligibility`, `None` when no extraction row exists yet — mirrors the lookup pattern `api/query.py` already uses.

**Dev workflow:** three local processes — `docker-compose up` (Postgres/Qdrant), `uvicorn` (API), `npm run dev` (frontend) — matching the project's existing local-only posture. No deployment concerns addressed here (spec 6, parked).

## Components

**`ChatQueryBox`** — single textarea + submit button, styled as a chat composer (avatar/icon, rounded bubble). Placeholder: "Describe your background and what you're looking for..." On submit, calls `useQuerySearch(query)` → `POST /query`. Owns only the current input text; no history.

**`ExtractionSummary`** — renders once `/query` returns, built from `extracted_filters` + `extracted_profile`. Each field (degree, grade, nationality, languages, fee-free, city) renders as a removable/editable chip. Editing a chip updates local `SearchFilters` state and calls `useFilteredSearch` (`POST /search` with the original `semantic_query` and the adjusted filters) rather than re-running `/query` — correcting a bad extraction is instant and doesn't re-invoke the LLM parser or eligibility reasoner. A "start over" action resets all state back to the empty `ChatQueryBox`. When `extracted_filters`/`extracted_profile` come back `null` (Layer 2 parse-failure degradation on the backend), this renders a plain notice instead of chips — see Error Handling.

**`ResultsList` / `ResultCard`** — renders the current result set (`QueryResult[]` after the initial `/query`, or `SearchResult[]` merged with cached verdicts after a chip edit — see Data Flow). Each card shows course name, university, city, languages, tuition/deadline text, and a color-coded eligibility badge (`eligible` / `likely_eligible` / `not_eligible` / `unclear` / `no_data`) with a one-line reasoning excerpt. Clicking a card opens `AdmissionGuideDrawer` for that program's id.

**`AdmissionGuideDrawer`** — slide-in side panel (results list stays visible behind it, preserving browsing context; supports flipping between programs without losing place). Opening it calls `useProgramDetail(id)` (`GET /programs/{id}`). Shows the verdict + full reasoning (passed down from the already-held `QueryResult`, not refetched), then the structured admission guide from `structured_eligibility` — grade requirement, language requirements, standardized tests, degree prerequisite — each as a labeled row with its `source_quote` shown as supporting text. Falls back to rendering raw `raw_sections` text when `structured_eligibility` is `null`.

## Data Flow

**Initial submit:** `ChatQueryBox` submit → `POST /query` → response populates `ExtractionSummary` (chips) and `ResultsList` (`QueryResult[]`, each already carrying its own `eligibility_verdict`/`eligibility_reasoning`). This call can take a few seconds (LLM parse + reasoning, possibly through the provider fallback chain) — see Error Handling.

**Chip edit:** Editing/removing a chip updates local `SearchFilters` → `POST /search` with the adjusted filters and the original `semantic_query`. This returns plain `SearchResult[]`, with no eligibility data. To keep verdicts visible without a fresh reasoning call, the frontend keeps a `Map<programId, EligibilityVerdict>` built from the original `/query` response and merges it into the new result list by id. A program present in the filtered results but absent from that map (i.e. it wasn't in the original reasoning pool) renders with `eligibility_verdict: "no_data"` — consistent with the backend's existing use of `"no_data"` to mean "no verdict available for this one," regardless of the specific reason. No LLM reasoning call is triggered by a chip edit.

**Program click:** Opens `AdmissionGuideDrawer`, triggers `GET /programs/{id}` (cached by TanStack Query per session, so revisiting a program doesn't refetch). Verdict/reasoning shown come from the already-held `QueryResult`, not this fetch.

**"Start over":** Clears query text, chips, results, and the verdict map back to the initial empty state.

## Error Handling

- **`/query` latency:** `ResultsList` shows a loading/skeleton state with copy like "Reading your profile and checking eligibility — this can take a few seconds," setting expectations given the backend's LLM fallback chain.
- **Parse-failure degradation (backend Layer 2):** when `extracted_filters`/`extracted_profile` are `null`, `ExtractionSummary` shows a plain notice ("Couldn't extract structured details from your query, showing closest matches instead") instead of empty/broken chips. Results still render normally.
- **Reasoning failures:** already surfaced by the backend as `"unclear"` verdicts with an explanatory `reasoning` string — no special frontend handling beyond rendering the badge as-is.
- **Network/5xx errors** (any of `/query`, `/search`, `/programs/{id}`): an inline error banner with a retry button that re-fires the same request (via TanStack Query's error state). A failed chip-edit `/search` call leaves the previous chips/results in place rather than clearing them.
- **Empty results** (`total_matched: 0`): a distinct empty state ("No programs matched — try loosening a filter or rephrasing") rather than a blank list.
- **Drawer fetch failure:** a `GET /programs/{id}` error renders inline inside the open drawer without closing it. A `null` `structured_eligibility` falls back to raw `raw_sections` text, as covered in Components.

## Testing

Vitest + React Testing Library, with MSW (Mock Service Worker) stubbing `/query`, `/search`, and `/programs/{id}` — no real backend needed to run the suite. Coverage focus:
- `ChatQueryBox` submits and shows its loading state
- `ExtractionSummary` chip edits fire `/search` with the correctly adjusted filters, and the verdict-merge-by-id logic (including the `"no_data"` fallback for a program outside the original reasoning pool)
- `ResultsList`/`ResultCard` renders each verdict badge correctly, and the empty-results state
- `AdmissionGuideDrawer` renders structured data when present and falls back to `raw_sections` when `structured_eligibility` is `null`

No E2E (Playwright etc.) for v1 — YAGNI given this is a single-flow app well covered at the component level; revisit if the app grows more routes/flows.

## Tech Stack

- React + Vite + TypeScript
- Tailwind CSS + shadcn/ui
- TanStack Query (server-state fetching/caching)
- Vitest + React Testing Library + MSW (testing)
- Backend: FastAPI `CORSMiddleware`; `ProgramDetail.structured_eligibility` sourced from spec 2's `Eligibility` table
