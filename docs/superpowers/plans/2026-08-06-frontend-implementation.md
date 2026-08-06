# Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A React + TypeScript single-page app (served by Vite) with a chat-style query box, an editable summary of what the backend understood from the query, an eligibility-annotated results list, and a structured admission-guide side panel per program — backed by the existing `/query`, `/search`, and `/programs/{id}` endpoints plus three small additive backend fields.

**Architecture:** A new `frontend/` directory (own `package.json`, independent of the Python backend's lifecycle) with a typed API client wrapping the three endpoints, TanStack Query hooks around that client, and presentational components composed in `App.tsx`. The one client-side merge concern — reattaching cached eligibility verdicts to a `/search`-only result set after a chip edit — is a pure, independently tested function (`mergeVerdicts`).

**Tech Stack:** React 18, Vite, TypeScript (strict), Tailwind CSS, Radix UI (`@radix-ui/react-dialog` for the side panel), `@tanstack/react-query`, Vitest + React Testing Library + MSW for tests. Backend: FastAPI, SQLAlchemy (existing stack, three additive touches only).

## Global Constraints

- The frontend lives entirely under `frontend/`, with its own `package.json` — never add JS dependencies to the root `pyproject.toml`, and never import Python files from `frontend/` or vice versa.
- TypeScript `strict: true`. No `any` in the code written by this plan (`unknown` + narrowing, or exact types, everywhere).
- `frontend/src/types.ts` hand-mirrors the backend's Pydantic schemas field-for-field. There is no codegen step in this plan — if a backend schema changes later, `types.ts` must be updated by hand to match. Field names are copied verbatim (snake_case), not renamed to camelCase, so the JSON from `fetch` needs no key translation.
- The design spec calls for "Tailwind CSS + shadcn/ui." This plan hand-authors the small set of UI primitives needed (styled buttons, chips, skeletons, a Radix-`Dialog`-based side panel) directly in Tailwind + Radix rather than running the `shadcn` CLI, which fetches component source from a network registry at generation time — not reproducible from a written plan. The result is functionally and visually equivalent (Radix primitives + Tailwind, the same materials shadcn itself uses), just without the CLI step.
- All server-data fetching goes through the hooks built in Task 3 (`useQuerySearch`, `useFilteredSearch`, `useProgramDetail`) — no component calls `fetch` or the API client directly.
- Tests run non-interactively: `cd frontend && npm test` runs `vitest run` (not watch mode). Every task's frontend tests must pass this way before moving on.
- The backend touch (Task 1) reuses this project's existing test conventions exactly: `pytest.mark.integration`, the `api_client`/`seeded_session_factory`/`make_program` fixtures from `tests/conftest.py`, and `.venv/bin/python -m pytest` (never bare `python`/`pytest` — see the existing plans' note that system Python on this machine is 3.9.6).
- Per this project's UI-verification convention: after Task 8, the dev servers must actually be started and the flow exercised in a real browser — passing tests alone does not establish the feature works end-to-end.

## File Structure

Backend (Task 1):
- `src/daad_search/config.py` — gains `cors_allowed_origins: list[str]`
- `src/daad_search/api/main.py` — gains `CORSMiddleware`, `GET /programs/{id}` gains the `Eligibility` lookup
- `src/daad_search/api/schemas.py` — `ProgramDetail` gains `structured_eligibility: dict | None`
- `src/daad_search/query_understanding/schema.py` — `QueryResponse` gains `semantic_query: str | None`
- `src/daad_search/api/query.py` — `handle_query` sets the new field on its return value
- `tests/test_search_api.py` — new tests for both endpoint changes
- `tests/test_query_api.py` — one assertion extended for the new field

Frontend:
- `frontend/package.json`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `vite.config.ts`, `postcss.config.js`, `tailwind.config.ts`, `index.html` — project scaffold (Task 2)
- `frontend/src/main.tsx`, `src/index.css`, `src/vite-env.d.ts` — entry point (Task 2)
- `frontend/src/types.ts` — hand-mirrored backend schemas (Task 2)
- `frontend/src/api/client.ts` — `postQuery`, `postSearch`, `getProgram` (Task 2)
- `frontend/src/test/setup.ts`, `src/test/mswServer.ts` — shared test infrastructure (Task 2)
- `frontend/src/App.tsx` — minimal in Task 2, fully wired in Task 8
- `frontend/src/hooks/useQuerySearch.ts`, `useFilteredSearch.ts`, `useProgramDetail.ts` (Task 3)
- `frontend/src/components/ChatQueryBox.tsx` (Task 4)
- `frontend/src/components/ExtractionSummary.tsx` (Task 5)
- `frontend/src/lib/mergeVerdicts.ts`, `src/components/ResultCard.tsx`, `src/components/ResultsList.tsx` (Task 6)
- `frontend/src/components/AdmissionGuideDrawer.tsx` (Task 7)
- `frontend/src/App.tsx` — full wiring (Task 8, modifies Task 2's version)
- `.gitignore` (root) — gains `frontend/node_modules/`, `frontend/dist/` (Task 2)

---

### Task 1: Backend touch — CORS, structured_eligibility, semantic_query

**Files:**
- Modify: `src/daad_search/config.py`
- Modify: `src/daad_search/api/main.py`
- Modify: `src/daad_search/api/schemas.py`
- Modify: `src/daad_search/query_understanding/schema.py`
- Modify: `src/daad_search/api/query.py`
- Modify: `tests/test_search_api.py`
- Modify: `tests/test_query_api.py`

**Interfaces:**
- Consumes: `daad_search.db.models.Eligibility` (existing), `daad_search.config.settings` (existing)
- Produces: `Settings.cors_allowed_origins: list[str]`; `ProgramDetail.structured_eligibility: dict | None`; `QueryResponse.semantic_query: str | None` — all three read directly as JSON fields by the frontend built in later tasks.

- [ ] **Step 1: Write the failing tests**

`tests/test_search_api.py` already has `import pytest` and `pytestmark = pytest.mark.integration` at the top — leave those as they are. Add two more imports right after `import pytest`:

```python
import asyncio
from datetime import datetime, timezone

from daad_search.db.models import Eligibility
```

Then add this helper function anywhere at module level (e.g. right after the `TWO_PROGRAMS` constant):

```python
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
```

Append these three tests at the end of the file:

```python
@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_includes_structured_eligibility_when_present(api_client, seeded_session_factory):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})

    response = api_client.get("/programs/1")

    assert response.status_code == 200
    assert response.json()["structured_eligibility"] == {"grade_requirement": {"value": 2.5}}


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_structured_eligibility_is_none_when_absent(api_client):
    response = api_client.get("/programs/1")

    assert response.status_code == 200
    assert response.json()["structured_eligibility"] is None


def test_cors_allows_the_configured_frontend_origin(api_client):
    response = api_client.options(
        "/search",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

Add one assertion to the existing `test_query_reasoning_failure_returns_unclear_verdicts` in `tests/test_query_api.py` — find this line near the end of that test:

```python
    assert body["extracted_profile"]["nationality"] == "Pakistan"
```

and add directly after it:

```python
    assert body["semantic_query"] is None  # this test's ParsedQuery mock never sets it
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_search_api.py tests/test_query_api.py -v -m integration`
Expected: the three new tests FAIL (`KeyError: 'structured_eligibility'` or a 400/plain CORS-header-missing assertion failure), and the modified `test_query_reasoning_failure_returns_unclear_verdicts` FAILS with `KeyError: 'semantic_query'`.

- [ ] **Step 3: Write the implementation**

Add to `src/daad_search/config.py`, right after `openai_api_key: str = ""`:

```python
    # Origins allowed to call this API cross-origin. Vite's default dev port
    # is 5173 -- the frontend's dev server runs there unless overridden.
    cors_allowed_origins: list[str] = ["http://localhost:5173"]
```

Modify `src/daad_search/api/schemas.py` — add one field to `ProgramDetail`:

```python
class ProgramDetail(SearchResult):
    course_type: int
    degree: str | None
    duration: str | None
    beginning: str | None
    raw_sections: dict
    structured_eligibility: dict | None = None
```

Modify `src/daad_search/query_understanding/schema.py` — add one field to `QueryResponse`:

```python
class QueryResponse(BaseModel):
    results: list[QueryResult]
    total_matched: int
    extracted_filters: SearchFilters | None = None
    extracted_profile: StudentProfile | None = None
    semantic_query: str | None = None
```

Modify `src/daad_search/api/query.py` — `handle_query`'s final `return` statement gains one line:

```python
    return QueryResponse(
        results=query_results,
        total_matched=total,
        extracted_filters=filters if parsed is not None else None,
        extracted_profile=profile,
        semantic_query=semantic_query if parsed is not None else None,
    )
```

Modify `src/daad_search/api/main.py`:

```python
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.models import Eligibility, Program
from ..db.session import async_session_factory
from ..query_understanding.schema import QueryRequest, QueryResponse
from .query import handle_query
from .schemas import ProgramDetail, SearchRequest, SearchResponse
from .search import filtered_search, hybrid_search, to_search_result

app = FastAPI(title="DAAD Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

(Only the import block and the `app.add_middleware(...)` call are new; everything from `async def get_session` through the `/search` route stays exactly as it is.)

Then update the `get_program` route:

```python
@app.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> ProgramDetail:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    eligibility = await session.get(Eligibility, program_id)

    base = to_search_result(row)
    return ProgramDetail(
        **base.model_dump(),
        course_type=row.course_type,
        degree=row.degree,
        duration=row.duration,
        beginning=row.beginning,
        raw_sections=row.raw_sections,
        structured_eligibility=eligibility.structured_eligibility if eligibility else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_search_api.py tests/test_query_api.py -v -m integration`
Expected: PASS (all tests in both files).

Then run the full suite to confirm nothing else regressed: `.venv/bin/python -m pytest -v -m "not integration"` and `.venv/bin/python -m pytest -v -m integration` (the same 5 pre-existing environment failures from placeholder `VOYAGE_API_KEY`/blocked `GROQ_API_KEY` are expected and not a regression — see `docs/superpowers/specs/2026-08-06-query-understanding-design.md`'s history for context if unfamiliar).

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/config.py src/daad_search/api/main.py src/daad_search/api/schemas.py src/daad_search/query_understanding/schema.py src/daad_search/api/query.py tests/test_search_api.py tests/test_query_api.py
git commit -m "feat: CORS, structured_eligibility, and semantic_query for the frontend"
```

---

### Task 2: Frontend scaffold, types, and API client

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/postcss.config.js`, `frontend/tailwind.config.ts`, `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/index.css`, `frontend/src/vite-env.d.ts`, `frontend/src/App.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/test/setup.ts`, `frontend/src/test/mswServer.ts`
- Test: `frontend/src/api/client.test.ts`
- Modify: `.gitignore` (root)

**Interfaces:**
- Consumes: the three backend response shapes from Task 1 (`SearchResponse`, `QueryResponse`, `ProgramDetail`)
- Produces: TS types `SearchFilters`, `StudentProfile`, `SearchResult`, `QueryResult`, `SearchResponse`, `QueryResponse`, `ProgramDetail`, `StructuredEligibility` (and its nested types) in `types.ts`; functions `postQuery(query: string, limit?: number): Promise<QueryResponse>`, `postSearch(filters: SearchFilters, semanticQuery: string | null, limit?: number): Promise<SearchResponse>`, `getProgram(id: number): Promise<ProgramDetail>` in `api/client.ts`

- [ ] **Step 1: Create the project scaffold files**

`frontend/package.json`:

```json
{
  "name": "daad-search-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "@radix-ui/react-dialog": "^1.1.4",
    "@tanstack/react-query": "^5.62.0",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.17",
    "@types/react-dom": "^18.3.5",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^25.0.1",
    "msw": "^2.6.8",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.2",
    "vite": "^6.0.5",
    "vitest": "^2.1.8"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

`frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

`frontend/vite.config.ts`:

```ts
/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
  },
});
```

`frontend/postcss.config.js`:

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

`frontend/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>DAAD Program Search</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`frontend/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

`frontend/src/main.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

`frontend/src/App.tsx` (minimal for now — Task 8 replaces this entirely):

```tsx
export default function App() {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold text-slate-900">DAAD Program Search</h1>
    </main>
  );
}
```

Add to the root `.gitignore` (append, don't remove any existing lines):

```
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && npm install`
Expected: `node_modules/` populated, `package-lock.json` created, no errors.

- [ ] **Step 3: Write the failing test**

`frontend/src/test/mswServer.ts`:

```ts
import { setupServer } from "msw/node";

export const mswServer = setupServer();
```

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll } from "vitest";

import { mswServer } from "./mswServer";

beforeAll(() => mswServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => mswServer.resetHandlers());
afterAll(() => mswServer.close());
```

`frontend/src/api/client.test.ts`:

```ts
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { mswServer } from "../test/mswServer";
import { getProgram, postQuery, postSearch } from "./client";

const API_BASE_URL = "http://localhost:8000";

describe("api client", () => {
  it("postQuery sends the query and limit, and returns the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ query: "robotics masters", limit: 20 });
        return HttpResponse.json({
          results: [], total_matched: 0, extracted_filters: null, extracted_profile: null, semantic_query: null,
        });
      }),
    );

    const result = await postQuery("robotics masters");
    expect(result.total_matched).toBe(0);
  });

  it("postSearch sends filters and semantic_query, and returns the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/search`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({
          filters: { languages: ["English"] }, semantic_query: "robotics", limit: 20,
        });
        return HttpResponse.json({ results: [], total_matched: 0 });
      }),
    );

    const result = await postSearch({ languages: ["English"] }, "robotics");
    expect(result.total_matched).toBe(0);
  });

  it("getProgram fetches a program by id", async () => {
    mswServer.use(
      http.get(`${API_BASE_URL}/programs/10396`, () =>
        HttpResponse.json({
          id: 10396, course_name: "Additive Manufacturing", university: "TU X", city: null,
          languages: ["English"], subject: null, tuition_fees_text: null,
          application_deadline_text: null, link: "https://example.com", score: null,
          course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: {}, structured_eligibility: null,
        }),
      ),
    );

    const result = await getProgram(10396);
    expect(result.course_name).toBe("Additive Manufacturing");
  });

  it("throws when the response is not ok", async () => {
    mswServer.use(
      http.get(`${API_BASE_URL}/programs/999`, () => new HttpResponse(null, { status: 404 })),
    );

    await expect(getProgram(999)).rejects.toThrow("GET /programs/999 failed with 404");
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: FAIL — `src/api/client.ts` and `src/types.ts` don't exist yet.

- [ ] **Step 5: Write the implementation**

`frontend/src/types.ts`:

```ts
export interface SearchFilters {
  languages?: string[] | null;
  max_tuition_free_only?: boolean | null;
  subject?: string | null;
  city?: string | null;
  course_type?: number | null;
}

export interface StudentProfile {
  degree_field?: string | null;
  grade_value?: number | null;
  grade_scale?: string | null;
  nationality?: string | null;
  other_notes?: string | null;
}

export type EligibilityVerdictValue = "eligible" | "likely_eligible" | "not_eligible" | "unclear" | "no_data";

export interface SearchResult {
  id: number;
  course_name: string;
  university: string;
  city: string | null;
  languages: string[];
  subject: string | null;
  tuition_fees_text: string | null;
  application_deadline_text: string | null;
  link: string;
  score: number | null;
}

export interface SearchResponse {
  results: SearchResult[];
  total_matched: number;
}

export interface QueryResult extends SearchResult {
  eligibility_verdict: EligibilityVerdictValue;
  eligibility_reasoning: string | null;
}

export interface QueryResponse {
  results: QueryResult[];
  total_matched: number;
  extracted_filters: SearchFilters | null;
  extracted_profile: StudentProfile | null;
  semantic_query: string | null;
}

export interface SubScore {
  section: string;
  min_score: number;
}

export interface StandardizedTest {
  test: string;
  required: boolean;
  eligibility_condition: string | null;
  subscores: SubScore[];
  waiver: string | null;
  source_quote: string;
}

export interface AcceptedTest {
  test_name: string;
  min_score: string;
}

export interface LanguageRequirement {
  language: string;
  level: string;
  accepted_tests: AcceptedTest[];
  source_quote: string;
}

export interface GradeRequirement {
  value: number | null;
  scale: string | null;
  source_quote: string | null;
}

export interface DegreePrerequisite {
  description: string;
  source_quote: string;
}

export interface StructuredEligibility {
  requires_gre: boolean | null;
  requires_gmat: boolean | null;
  min_german_level: string | null;
  min_english_level: string | null;
  extraction_confidence: "high" | "medium" | "low";
  degree_prerequisite: DegreePrerequisite | null;
  grade_requirement: GradeRequirement | null;
  standardized_tests: StandardizedTest[];
  language_requirements: LanguageRequirement[];
  notes: string | null;
}

export interface ProgramDetail extends SearchResult {
  course_type: number;
  degree: string | null;
  duration: string | null;
  beginning: string | null;
  raw_sections: Record<string, string>;
  structured_eligibility: StructuredEligibility | null;
}
```

`frontend/src/api/client.ts`:

```ts
import type { ProgramDetail, QueryResponse, SearchFilters, SearchResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function postQuery(query: string, limit = 20): Promise<QueryResponse> {
  return request<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
}

export function postSearch(
  filters: SearchFilters, semanticQuery: string | null, limit = 20,
): Promise<SearchResponse> {
  return request<SearchResponse>("/search", {
    method: "POST",
    body: JSON.stringify({ filters, semantic_query: semanticQuery, limit }),
  });
}

export function getProgram(id: number): Promise<ProgramDetail> {
  return request<ProgramDetail>(`/programs/${id}`);
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add frontend .gitignore
git commit -m "feat: frontend scaffold, typed schemas, and API client"
```

---

### Task 3: TanStack Query hooks

**Files:**
- Create: `frontend/src/hooks/useQuerySearch.ts`, `frontend/src/hooks/useFilteredSearch.ts`, `frontend/src/hooks/useProgramDetail.ts`
- Test: `frontend/src/hooks/hooks.test.tsx`

**Interfaces:**
- Consumes: `postQuery`, `postSearch`, `getProgram` (Task 2)
- Produces: `useQuerySearch()` (a `useMutation` result whose `mutate`/`mutateAsync` take `(query: string)` and resolve to `QueryResponse`); `useFilteredSearch()` (a `useMutation` result whose `mutate`/`mutateAsync` take `({ filters: SearchFilters; semanticQuery: string | null })` and resolve to `SearchResponse`); `useProgramDetail(programId: number | null)` (a `useQuery` result, `enabled` only when `programId !== null`, keyed `["program", programId]`)

- [ ] **Step 1: Write the failing test**

`frontend/src/hooks/hooks.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { PropsWithChildren } from "react";
import { describe, expect, it } from "vitest";

import { mswServer } from "../test/mswServer";
import { useFilteredSearch } from "./useFilteredSearch";
import { useProgramDetail } from "./useProgramDetail";
import { useQuerySearch } from "./useQuerySearch";

const API_BASE_URL = "http://localhost:8000";

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useQuerySearch", () => {
  it("posts the query and exposes the result via mutateAsync", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, () =>
        HttpResponse.json({
          results: [], total_matched: 3, extracted_filters: null, extracted_profile: null, semantic_query: null,
        }),
      ),
    );
    const { result } = renderHook(() => useQuerySearch(), { wrapper });

    const response = await result.current.mutateAsync("robotics masters");
    expect(response.total_matched).toBe(3);
  });
});

describe("useFilteredSearch", () => {
  it("posts filters and exposes the result via mutateAsync", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/search`, () => HttpResponse.json({ results: [], total_matched: 1 })),
    );
    const { result } = renderHook(() => useFilteredSearch(), { wrapper });

    const response = await result.current.mutateAsync({
      filters: { languages: ["English"] }, semanticQuery: null,
    });
    expect(response.total_matched).toBe(1);
  });
});

describe("useProgramDetail", () => {
  it("does not fetch when programId is null", () => {
    const { result } = renderHook(() => useProgramDetail(null), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("fetches the program when programId is set", async () => {
    mswServer.use(
      http.get(`${API_BASE_URL}/programs/10396`, () =>
        HttpResponse.json({
          id: 10396, course_name: "Additive Manufacturing", university: "TU X", city: null,
          languages: ["English"], subject: null, tuition_fees_text: null,
          application_deadline_text: null, link: "https://example.com", score: null,
          course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: {}, structured_eligibility: null,
        }),
      ),
    );
    const { result } = renderHook(() => useProgramDetail(10396), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.course_name).toBe("Additive Manufacturing");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/hooks/hooks.test.tsx`
Expected: FAIL — the three hook modules don't exist yet.

- [ ] **Step 3: Write the implementation**

`frontend/src/hooks/useQuerySearch.ts`:

```ts
import { useMutation } from "@tanstack/react-query";

import { postQuery } from "../api/client";

export function useQuerySearch() {
  return useMutation({
    mutationFn: (query: string) => postQuery(query),
  });
}
```

`frontend/src/hooks/useFilteredSearch.ts`:

```ts
import { useMutation } from "@tanstack/react-query";

import { postSearch } from "../api/client";
import type { SearchFilters } from "../types";

export function useFilteredSearch() {
  return useMutation({
    mutationFn: ({ filters, semanticQuery }: { filters: SearchFilters; semanticQuery: string | null }) =>
      postSearch(filters, semanticQuery),
  });
}
```

`frontend/src/hooks/useProgramDetail.ts`:

```ts
import { useQuery } from "@tanstack/react-query";

import { getProgram } from "../api/client";

export function useProgramDetail(programId: number | null) {
  return useQuery({
    queryKey: ["program", programId],
    queryFn: () => getProgram(programId as number),
    enabled: programId !== null,
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/hooks/hooks.test.tsx`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks
git commit -m "feat: TanStack Query hooks for query, search, and program-detail fetching"
```

---

### Task 4: ChatQueryBox component

**Files:**
- Create: `frontend/src/components/ChatQueryBox.tsx`
- Test: `frontend/src/components/ChatQueryBox.test.tsx`

**Interfaces:**
- Produces: `<ChatQueryBox onSubmit={(query: string) => void} isPending={boolean} />`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/ChatQueryBox.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatQueryBox } from "./ChatQueryBox";

describe("ChatQueryBox", () => {
  it("calls onSubmit with the trimmed query text", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.type(
      screen.getByPlaceholderText(/describe your background/i),
      "  bachelors in AI, CGPA 3.2  ",
    );
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalledWith("bachelors in AI, CGPA 3.2");
  });

  it("does not call onSubmit for empty or whitespace-only input", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "   ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows loading copy while pending", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={true} />);

    expect(screen.getByRole("button", { name: /reading your profile/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/ChatQueryBox.test.tsx`
Expected: FAIL — `ChatQueryBox.tsx` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

`frontend/src/components/ChatQueryBox.tsx`:

```tsx
import { type FormEvent, useState } from "react";

interface ChatQueryBoxProps {
  onSubmit: (query: string) => void;
  isPending: boolean;
}

export function ChatQueryBox({ onSubmit, isPending }: ChatQueryBoxProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Describe your background and what you're looking for..."
        rows={3}
        className="resize-none rounded-lg border border-slate-200 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
      />
      <button
        type="submit"
        disabled={isPending || query.trim().length === 0}
        className="self-end rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isPending ? "Reading your profile and checking eligibility..." : "Search programs"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/components/ChatQueryBox.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChatQueryBox.tsx frontend/src/components/ChatQueryBox.test.tsx
git commit -m "feat: ChatQueryBox component"
```

---

### Task 5: ExtractionSummary component

**Files:**
- Create: `frontend/src/components/ExtractionSummary.tsx`
- Test: `frontend/src/components/ExtractionSummary.test.tsx`

**Interfaces:**
- Consumes: `SearchFilters`, `StudentProfile` (Task 2)
- Produces: `<ExtractionSummary filters={SearchFilters | null} profile={StudentProfile | null} onFiltersChange={(filters: SearchFilters) => void} />`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/ExtractionSummary.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExtractionSummary } from "./ExtractionSummary";

describe("ExtractionSummary", () => {
  it("renders a removable chip per non-null filter field", () => {
    render(
      <ExtractionSummary
        filters={{ languages: ["English"], max_tuition_free_only: true, subject: null, city: null, course_type: null }}
        profile={null}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Languages: English")).toBeInTheDocument();
    expect(screen.getByText("Tuition-free only")).toBeInTheDocument();
  });

  it("removing a filter chip calls onFiltersChange with that field nulled out", async () => {
    const onFiltersChange = vi.fn();
    render(
      <ExtractionSummary
        filters={{ languages: ["English"], max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={null}
        onFiltersChange={onFiltersChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /remove filter: languages: english/i }));

    expect(onFiltersChange).toHaveBeenCalledWith({
      languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null,
    });
  });

  it("renders profile fields as read-only chips with no remove control", () => {
    render(
      <ExtractionSummary
        filters={{ languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={{
          degree_field: "Artificial Intelligence", grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)",
          nationality: "Pakistan", other_notes: null,
        }}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Degree: Artificial Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Grade: 3.2 (4.0 GPA scale (USA))")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove.*degree/i })).not.toBeInTheDocument();
  });

  it("shows a fallback notice when both filters and profile are null", () => {
    render(<ExtractionSummary filters={null} profile={null} onFiltersChange={vi.fn()} />);
    expect(screen.getByText(/couldn't extract structured details/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/ExtractionSummary.test.tsx`
Expected: FAIL — `ExtractionSummary.tsx` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

`frontend/src/components/ExtractionSummary.tsx`:

```tsx
import type { SearchFilters, StudentProfile } from "../types";

interface FilterChip {
  key: keyof SearchFilters;
  label: string;
}

function buildFilterChips(filters: SearchFilters): FilterChip[] {
  const chips: FilterChip[] = [];
  if (filters.languages && filters.languages.length > 0) {
    chips.push({ key: "languages", label: `Languages: ${filters.languages.join(", ")}` });
  }
  if (filters.max_tuition_free_only) {
    chips.push({ key: "max_tuition_free_only", label: "Tuition-free only" });
  }
  if (filters.subject) {
    chips.push({ key: "subject", label: `Subject: ${filters.subject}` });
  }
  if (filters.city) {
    chips.push({ key: "city", label: `City: ${filters.city}` });
  }
  if (filters.course_type != null) {
    chips.push({ key: "course_type", label: `Course type: ${filters.course_type}` });
  }
  return chips;
}

function buildProfileChips(profile: StudentProfile): string[] {
  const chips: string[] = [];
  if (profile.degree_field) chips.push(`Degree: ${profile.degree_field}`);
  if (profile.grade_value != null) {
    chips.push(`Grade: ${profile.grade_value}${profile.grade_scale ? ` (${profile.grade_scale})` : ""}`);
  }
  if (profile.nationality) chips.push(`Nationality: ${profile.nationality}`);
  if (profile.other_notes) chips.push(profile.other_notes);
  return chips;
}

interface ExtractionSummaryProps {
  filters: SearchFilters | null;
  profile: StudentProfile | null;
  onFiltersChange: (filters: SearchFilters) => void;
}

export function ExtractionSummary({ filters, profile, onFiltersChange }: ExtractionSummaryProps) {
  if (filters === null && profile === null) {
    return (
      <p className="text-sm text-slate-500">
        Couldn't extract structured details from your query, showing closest matches instead.
      </p>
    );
  }

  const filterChips = filters ? buildFilterChips(filters) : [];
  const profileChips = profile ? buildProfileChips(profile) : [];

  function removeFilterChip(key: keyof SearchFilters) {
    if (!filters) return;
    onFiltersChange({ ...filters, [key]: null });
  }

  return (
    <div className="flex flex-wrap gap-2">
      {filterChips.map((chip) => (
        <span
          key={chip.key}
          className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
        >
          {chip.label}
          <button
            type="button"
            aria-label={`Remove filter: ${chip.label}`}
            onClick={() => removeFilterChip(chip.key)}
            className="ml-1 text-slate-400 hover:text-slate-700"
          >
            ×
          </button>
        </span>
      ))}
      {profileChips.map((label) => (
        <span
          key={label}
          className="inline-flex items-center rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-500"
        >
          {label}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/components/ExtractionSummary.test.tsx`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ExtractionSummary.tsx frontend/src/components/ExtractionSummary.test.tsx
git commit -m "feat: ExtractionSummary component with editable filter chips"
```

---

### Task 6: mergeVerdicts, ResultCard, and ResultsList

**Files:**
- Create: `frontend/src/lib/mergeVerdicts.ts`
- Create: `frontend/src/components/ResultCard.tsx`
- Create: `frontend/src/components/ResultsList.tsx`
- Test: `frontend/src/lib/mergeVerdicts.test.ts`, `frontend/src/components/ResultsList.test.tsx`

**Interfaces:**
- Consumes: `SearchResult`, `QueryResult` (Task 2)
- Produces: `buildVerdictMap(results: QueryResult[]): Map<number, VerdictInfo>`; `mergeVerdicts(results: SearchResult[], verdictMap: Map<number, VerdictInfo>): QueryResult[]`; `<ResultsList results={QueryResult[]} isLoading={boolean} onSelectProgram={(id: number) => void} />`

- [ ] **Step 1: Write the failing tests**

`frontend/src/lib/mergeVerdicts.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import type { QueryResult, SearchResult } from "../types";
import { buildVerdictMap, mergeVerdicts } from "./mergeVerdicts";

const BASE_RESULT: SearchResult = {
  id: 1, course_name: "Robotics MSc", university: "TU X", city: null, languages: ["English"],
  subject: null, tuition_fees_text: null, application_deadline_text: null, link: "https://example.com", score: null,
};

describe("buildVerdictMap / mergeVerdicts", () => {
  it("preserves the verdict for a program present in the original query results", () => {
    const original: QueryResult[] = [
      { ...BASE_RESULT, eligibility_verdict: "eligible", eligibility_reasoning: "meets all criteria" },
    ];
    const map = buildVerdictMap(original);

    const merged = mergeVerdicts([BASE_RESULT], map);

    expect(merged[0].eligibility_verdict).toBe("eligible");
    expect(merged[0].eligibility_reasoning).toBe("meets all criteria");
  });

  it("falls back to no_data for a program absent from the verdict map", () => {
    const map = buildVerdictMap([]);
    const merged = mergeVerdicts([{ ...BASE_RESULT, id: 99 }], map);

    expect(merged[0].eligibility_verdict).toBe("no_data");
    expect(merged[0].eligibility_reasoning).toBeNull();
  });
});
```

`frontend/src/components/ResultsList.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QueryResult } from "../types";
import { ResultsList } from "./ResultsList";

const RESULT: QueryResult = {
  id: 1, course_name: "Robotics MSc", university: "TU X", city: "Berlin", languages: ["English"],
  subject: null, tuition_fees_text: null, application_deadline_text: null, link: "https://example.com",
  score: null, eligibility_verdict: "eligible", eligibility_reasoning: "Meets the grade threshold.",
};

describe("ResultsList", () => {
  it("shows a loading skeleton while isLoading is true", () => {
    render(<ResultsList results={[]} isLoading={true} onSelectProgram={vi.fn()} />);
    expect(screen.getByTestId("results-loading")).toBeInTheDocument();
  });

  it("shows the empty state when there are no results", () => {
    render(<ResultsList results={[]} isLoading={false} onSelectProgram={vi.fn()} />);
    expect(screen.getByText(/no programs matched/i)).toBeInTheDocument();
  });

  it("renders a card per result with its verdict badge, and calls onSelectProgram when clicked", async () => {
    const onSelectProgram = vi.fn();
    render(<ResultsList results={[RESULT]} isLoading={false} onSelectProgram={onSelectProgram} />);

    expect(screen.getByText("Robotics MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Robotics MSc"));
    expect(onSelectProgram).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/lib/mergeVerdicts.test.ts src/components/ResultsList.test.tsx`
Expected: FAIL — none of the three modules exist yet.

- [ ] **Step 3: Write the implementation**

`frontend/src/lib/mergeVerdicts.ts`:

```ts
import type { EligibilityVerdictValue, QueryResult, SearchResult } from "../types";

export interface VerdictInfo {
  verdict: EligibilityVerdictValue;
  reasoning: string | null;
}

export function buildVerdictMap(results: QueryResult[]): Map<number, VerdictInfo> {
  return new Map(results.map((r) => [r.id, { verdict: r.eligibility_verdict, reasoning: r.eligibility_reasoning }]));
}

export function mergeVerdicts(results: SearchResult[], verdictMap: Map<number, VerdictInfo>): QueryResult[] {
  return results.map((r) => {
    const info = verdictMap.get(r.id);
    return {
      ...r,
      eligibility_verdict: info?.verdict ?? "no_data",
      eligibility_reasoning: info?.reasoning ?? null,
    };
  });
}
```

`frontend/src/components/ResultCard.tsx`:

```tsx
import type { QueryResult } from "../types";

const VERDICT_STYLES: Record<QueryResult["eligibility_verdict"], string> = {
  eligible: "bg-green-100 text-green-800",
  likely_eligible: "bg-lime-100 text-lime-800",
  not_eligible: "bg-red-100 text-red-800",
  unclear: "bg-amber-100 text-amber-800",
  no_data: "bg-slate-100 text-slate-600",
};

const VERDICT_LABELS: Record<QueryResult["eligibility_verdict"], string> = {
  eligible: "Eligible",
  likely_eligible: "Likely eligible",
  not_eligible: "Not eligible",
  unclear: "Unclear",
  no_data: "Not evaluated",
};

interface ResultCardProps {
  result: QueryResult;
  onClick: (id: number) => void;
}

export function ResultCard({ result, onClick }: ResultCardProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(result.id)}
      className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-slate-400"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-slate-900">{result.course_name}</h3>
          <p className="text-sm text-slate-500">
            {result.university}{result.city ? ` — ${result.city}` : ""}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${VERDICT_STYLES[result.eligibility_verdict]}`}>
          {VERDICT_LABELS[result.eligibility_verdict]}
        </span>
      </div>
      {result.eligibility_reasoning && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{result.eligibility_reasoning}</p>
      )}
    </button>
  );
}
```

`frontend/src/components/ResultsList.tsx`:

```tsx
import type { QueryResult } from "../types";
import { ResultCard } from "./ResultCard";

interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  onSelectProgram: (id: number) => void;
}

export function ResultsList({ results, isLoading, onSelectProgram }: ResultsListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="results-loading">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-slate-500">No programs matched — try loosening a filter or rephrasing.</p>
    );
  }

  return (
    <div className="space-y-3">
      {results.map((result) => (
        <ResultCard key={result.id} result={result} onClick={onSelectProgram} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/lib/mergeVerdicts.test.ts src/components/ResultsList.test.tsx`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/mergeVerdicts.ts frontend/src/lib/mergeVerdicts.test.ts frontend/src/components/ResultCard.tsx frontend/src/components/ResultsList.tsx frontend/src/components/ResultsList.test.tsx
git commit -m "feat: verdict-merge logic and results list/card components"
```

---

### Task 7: AdmissionGuideDrawer component

**Files:**
- Create: `frontend/src/components/AdmissionGuideDrawer.tsx`
- Test: `frontend/src/components/AdmissionGuideDrawer.test.tsx`

**Interfaces:**
- Consumes: `ProgramDetail`, `QueryResult`, `@radix-ui/react-dialog` (Task 2)
- Produces: `<AdmissionGuideDrawer programId={number | null} verdict={Pick<QueryResult, "eligibility_verdict" | "eligibility_reasoning"> | null} program={ProgramDetail | undefined} isLoading={boolean} isError={boolean} onClose={() => void} />`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/AdmissionGuideDrawer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ProgramDetail } from "../types";
import { AdmissionGuideDrawer } from "./AdmissionGuideDrawer";

const BASE_PROGRAM: ProgramDetail = {
  id: 10396, course_name: "Additive Manufacturing", university: "TU X", city: null, languages: ["English"],
  subject: null, tuition_fees_text: null, application_deadline_text: null, link: "https://example.com", score: null,
  course_type: 2, degree: null, duration: null, beginning: null, raw_sections: {}, structured_eligibility: null,
};

describe("AdmissionGuideDrawer", () => {
  it("renders nothing (closed) when programId is null", () => {
    render(
      <AdmissionGuideDrawer programId={null} verdict={null} program={undefined} isLoading={false} isError={false} onClose={vi.fn()} />,
    );
    expect(screen.queryByText("Admission guide")).not.toBeInTheDocument();
  });

  it("shows the loading state", () => {
    render(
      <AdmissionGuideDrawer programId={10396} verdict={null} program={undefined} isLoading={true} isError={false} onClose={vi.fn()} />,
    );
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows the error state", () => {
    render(
      <AdmissionGuideDrawer programId={10396} verdict={null} program={undefined} isLoading={false} isError={true} onClose={vi.fn()} />,
    );
    expect(screen.getByText(/couldn't load this program/i)).toBeInTheDocument();
  });

  it("falls back to raw_sections when structured_eligibility is null", () => {
    render(
      <AdmissionGuideDrawer
        programId={10396} verdict={null} isLoading={false} isError={false} onClose={vi.fn()}
        program={{ ...BASE_PROGRAM, raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." } }}
      />,
    );
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });

  it("renders structured requirements with their source quotes when present", () => {
    render(
      <AdmissionGuideDrawer
        programId={10396} verdict={null} isLoading={false} isError={false} onClose={vi.fn()}
        program={{
          ...BASE_PROGRAM,
          structured_eligibility: {
            requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: "B2",
            extraction_confidence: "high", degree_prerequisite: null,
            grade_requirement: { value: 2.5, scale: "German grading scale", source_quote: "A grade of 2.5 or better is required." },
            standardized_tests: [], language_requirements: [], notes: null,
          },
        }}
      />,
    );
    expect(screen.getByText(/grade requirement: 2.5/i)).toBeInTheDocument();
    expect(screen.getByText(/a grade of 2.5 or better is required/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/components/AdmissionGuideDrawer.test.tsx`
Expected: FAIL — `AdmissionGuideDrawer.tsx` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

`frontend/src/components/AdmissionGuideDrawer.tsx`:

```tsx
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import type { ProgramDetail, QueryResult } from "../types";

interface AdmissionGuideDrawerProps {
  programId: number | null;
  verdict: Pick<QueryResult, "eligibility_verdict" | "eligibility_reasoning"> | null;
  program: ProgramDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}

export function AdmissionGuideDrawer({
  programId, verdict, program, isLoading, isError, onClose,
}: AdmissionGuideDrawerProps) {
  return (
    <Dialog.Root open={programId !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">Admission guide</Dialog.Title>
            <Dialog.Close aria-label="Close" className="text-slate-400 hover:text-slate-700">
              <X size={18} />
            </Dialog.Close>
          </div>

          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-slate-500">Loading...</p>}

          {!isLoading && !isError && program && (
            <div className="space-y-4">
              {verdict && (
                <div>
                  <h3 className="text-sm font-medium text-slate-900">Eligibility</h3>
                  <p className="text-sm text-slate-600">{verdict.eligibility_reasoning ?? "No reasoning available."}</p>
                </div>
              )}

              {program.structured_eligibility ? (
                <StructuredAdmissionGuide eligibility={program.structured_eligibility} />
              ) : (
                <RawAdmissionText rawSections={program.raw_sections} />
              )}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function StructuredAdmissionGuide({
  eligibility,
}: {
  eligibility: NonNullable<ProgramDetail["structured_eligibility"]>;
}) {
  return (
    <div className="space-y-3">
      {eligibility.grade_requirement && (
        <RequirementRow
          label={`Grade requirement: ${eligibility.grade_requirement.value ?? "?"} (${eligibility.grade_requirement.scale ?? "scale not stated"})`}
          quote={eligibility.grade_requirement.source_quote}
        />
      )}
      {eligibility.language_requirements.map((req, index) => (
        <RequirementRow key={`${req.language}-${index}`} label={`${req.language}: ${req.level}`} quote={req.source_quote} />
      ))}
      {eligibility.standardized_tests.map((test, index) => (
        <RequirementRow
          key={`${test.test}-${index}`}
          label={`${test.test}: ${test.required ? "required" : "not required"}${test.eligibility_condition ? ` (${test.eligibility_condition})` : ""}`}
          quote={test.source_quote}
        />
      ))}
      {eligibility.degree_prerequisite && (
        <RequirementRow label={eligibility.degree_prerequisite.description} quote={eligibility.degree_prerequisite.source_quote} />
      )}
    </div>
  );
}

function RequirementRow({ label, quote }: { label: string; quote: string | null }) {
  return (
    <div className="rounded-lg border border-slate-100 p-3">
      <p className="text-sm font-medium text-slate-900">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-slate-500">"{quote}"</p>}
    </div>
  );
}

function RawAdmissionText({ rawSections }: { rawSections: Record<string, string> }) {
  const sections = Object.entries(rawSections).filter(([, text]) => text);
  if (sections.length === 0) {
    return <p className="text-sm text-slate-500">No admission text available for this program.</p>;
  }
  return (
    <div className="space-y-3">
      {sections.map(([key, text]) => (
        <div key={key}>
          <h4 className="text-xs font-medium uppercase text-slate-400">{key.replace(/_/g, " ")}</h4>
          <p className="text-sm text-slate-700">{text}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/components/AdmissionGuideDrawer.test.tsx`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AdmissionGuideDrawer.tsx frontend/src/components/AdmissionGuideDrawer.test.tsx
git commit -m "feat: AdmissionGuideDrawer component"
```

---

### Task 8: App wiring — full integration

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 2-7
- Produces: the fully wired `App` component — the plan's final deliverable

- [ ] **Step 1: Write the failing test**

`frontend/src/App.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import App from "./App";
import { mswServer } from "./test/mswServer";

const API_BASE_URL = "http://localhost:8000";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

const QUERY_RESPONSE = {
  results: [
    {
      id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
      languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
      link: "https://example.com/1", score: 0.9, eligibility_verdict: "eligible",
      eligibility_reasoning: "Meets the grade threshold.",
    },
  ],
  total_matched: 1,
  extracted_filters: { languages: ["English"], max_tuition_free_only: null, subject: null, city: null, course_type: null },
  extracted_profile: {
    degree_field: "Robotics", grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)", nationality: "Pakistan", other_notes: null,
  },
  semantic_query: "robotics",
};

describe("App", () => {
  it("submits a query, renders results, edits a chip to re-search, and opens the admission guide drawer", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, () => HttpResponse.json(QUERY_RESPONSE)),
      http.post(`${API_BASE_URL}/search`, async ({ request }) => {
        const body = (await request.json()) as { filters: Record<string, unknown> };
        expect(body.filters.languages).toBeNull();
        return HttpResponse.json({
          results: [{
            id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
            languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
            link: "https://example.com/1", score: 0.9,
          }],
          total_matched: 1,
        });
      }),
      http.get(`${API_BASE_URL}/programs/1`, () =>
        HttpResponse.json({
          id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
          languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
          link: "https://example.com/1", score: 0.9, course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: { admission_requirements: "A grade of 2.5 or better is required." }, structured_eligibility: null,
        }),
      ),
    );

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters, English taught");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.getByText("Languages: English")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /remove filter: languages: english/i }));

    await waitFor(() => expect(screen.queryByText("Languages: English")).not.toBeInTheDocument());
    expect(screen.getByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Robotics Engineering MSc"));

    expect(await screen.findByText(/a grade of 2.5 or better is required/i)).toBeInTheDocument();
    expect(
      within(screen.getByText("Eligibility").parentElement as HTMLElement).getByText(/meets the grade threshold/i),
    ).toBeInTheDocument();
  });

  it("start over resets the query, chips, results, and closes the drawer", async () => {
    mswServer.use(http.post(`${API_BASE_URL}/query`, () => HttpResponse.json(QUERY_RESPONSE)));

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));
    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /start over/i }));

    expect(screen.queryByText("Robotics Engineering MSc")).not.toBeInTheDocument();
    expect(screen.queryByText(/start over/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- src/App.test.tsx`
Expected: FAIL — `App.tsx` is still Task 2's minimal placeholder with no query box or results.

- [ ] **Step 3: Write the implementation**

`frontend/src/App.tsx` (replaces Task 2's version entirely):

```tsx
import { useState } from "react";

import { AdmissionGuideDrawer } from "./components/AdmissionGuideDrawer";
import { ChatQueryBox } from "./components/ChatQueryBox";
import { ExtractionSummary } from "./components/ExtractionSummary";
import { ResultsList } from "./components/ResultsList";
import { useFilteredSearch } from "./hooks/useFilteredSearch";
import { useProgramDetail } from "./hooks/useProgramDetail";
import { useQuerySearch } from "./hooks/useQuerySearch";
import { buildVerdictMap, mergeVerdicts, type VerdictInfo } from "./lib/mergeVerdicts";
import type { QueryResponse, QueryResult, SearchFilters } from "./types";

function ErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
      <span>Something went wrong.</span>
      <button type="button" onClick={onRetry} className="font-medium underline">
        Retry
      </button>
    </div>
  );
}

export default function App() {
  const [queryResponse, setQueryResponse] = useState<QueryResponse | null>(null);
  const [displayedResults, setDisplayedResults] = useState<QueryResult[]>([]);
  const [activeFilters, setActiveFilters] = useState<SearchFilters | null>(null);
  const [verdictMap, setVerdictMap] = useState<Map<number, VerdictInfo>>(new Map());
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null);

  const querySearch = useQuerySearch();
  const filteredSearch = useFilteredSearch();
  const programDetail = useProgramDetail(selectedProgramId);

  function handleSubmit(query: string) {
    querySearch.mutate(query, {
      onSuccess: (response) => {
        setQueryResponse(response);
        setDisplayedResults(response.results);
        setActiveFilters(response.extracted_filters);
        setVerdictMap(buildVerdictMap(response.results));
      },
    });
  }

  function handleFiltersChange(filters: SearchFilters) {
    filteredSearch.mutate(
      { filters, semanticQuery: queryResponse?.semantic_query ?? null },
      {
        onSuccess: (response) => {
          setActiveFilters(filters);
          setDisplayedResults(mergeVerdicts(response.results, verdictMap));
        },
      },
    );
  }

  function handleStartOver() {
    setQueryResponse(null);
    setDisplayedResults([]);
    setActiveFilters(null);
    setVerdictMap(new Map());
    setSelectedProgramId(null);
    querySearch.reset();
    filteredSearch.reset();
  }

  const hasSubmitted = querySearch.isPending || queryResponse !== null;
  const selectedVerdict = selectedProgramId !== null ? verdictMap.get(selectedProgramId) ?? null : null;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold text-slate-900">DAAD Program Search</h1>
      <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />

      {querySearch.isError && (
        <ErrorBanner onRetry={() => querySearch.variables !== undefined && querySearch.mutate(querySearch.variables)} />
      )}

      {hasSubmitted && (
        <>
          {queryResponse && (
            <div className="flex items-center justify-between gap-4">
              <ExtractionSummary
                filters={activeFilters}
                profile={queryResponse.extracted_profile}
                onFiltersChange={handleFiltersChange}
              />
              <button
                type="button"
                onClick={handleStartOver}
                className="shrink-0 text-sm text-slate-400 hover:text-slate-700"
              >
                Start over
              </button>
            </div>
          )}

          {filteredSearch.isError && (
            <ErrorBanner
              onRetry={() => filteredSearch.variables !== undefined && filteredSearch.mutate(filteredSearch.variables)}
            />
          )}

          <ResultsList
            results={displayedResults}
            isLoading={querySearch.isPending || filteredSearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />
        </>
      )}

      <AdmissionGuideDrawer
        programId={selectedProgramId}
        verdict={selectedVerdict}
        program={programDetail.data}
        isLoading={programDetail.isLoading}
        isError={programDetail.isError}
        onClose={() => setSelectedProgramId(null)}
      />
    </main>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- src/App.test.tsx`
Expected: PASS (2 passed).

Then run the whole frontend suite: `cd frontend && npm test`
Expected: PASS (every test file from Tasks 2-8).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: wire ChatQueryBox, ExtractionSummary, ResultsList, and AdmissionGuideDrawer into App"
```

---

## Final Verification

Run both suites from the repo root and from `frontend/`:

```bash
.venv/bin/python -m pytest -v -m "not integration"
.venv/bin/python -m pytest -v -m integration   # requires: docker compose up -d
cd frontend && npm test
cd frontend && npm run build   # tsc -b type-checks the whole app; catches anything vitest's jsdom run wouldn't
```

Then verify the real, wired-up feature in a browser — passing tests alone don't establish this, per this project's UI-verification convention:

```bash
docker compose up -d
uvicorn daad_search.api.main:app --reload &
cd frontend && npm run dev
```

Open the printed Vite URL (`http://localhost:5173` by default). Make sure at least one program in the catalog has extracted eligibility data first (`.venv/bin/python -m daad_search.cli extract --ids 10396` if not — see the eligibility-extraction plan for the CLI's shape). Then, in the browser:

1. Type a query like "I have a bachelors in AI from Pakistan with CGPA 3.2, want English-taught no-fee masters in Germany focused on machine learning" and submit — confirm results render with verdict badges, and the extraction chips reflect what was actually said.
2. Remove a filter chip — confirm the result list updates without the submit button re-entering its loading state for long (no LLM round-trip), and verdicts stay attached to the same programs.
3. Click a result card — confirm the admission guide panel slides in, shows the eligibility reasoning, and shows either structured requirement rows with quotes or the raw admission text, depending on whether that program has extracted eligibility data.
4. Click "Start over" — confirm the page resets to the empty query box.

At this point the frontend spec is fully implemented: a complete, tested, visually verified UI over the `/query`, `/search`, and `/programs/{id}` endpoints, closing out the fourth sub-project of the portfolio application. The next roadmap items (prerequisite/transcript matching, deployment) remain parked per the design spec.
