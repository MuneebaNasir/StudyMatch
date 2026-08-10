# Eligibility Cost Control & UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the seven items in `docs/superpowers/specs/2026-08-10-eligibility-and-ux-polish-design.md`: cut automatic eligibility reasoning to the top 1 candidate with an on-demand button for the rest, reorganize the admission guide's raw content into collapsible sections, add a pre-filled query template with degree-level example chips, stop rendering duplicate requirement text, surface the German-scale grade equivalent, add structured production logging, and replace the plain loading skeleton with a staged "turbo snail" indicator for the initial query.

**Architecture:** No new services or infrastructure. Backend changes are additive to the existing FastAPI app (`src/daad_search/api/`) and the LangChain-based query-understanding module (`src/daad_search/query_understanding/`). Frontend changes are additive to the existing React/Vite app (`frontend/src/`), adding one new npm dependency (`@radix-ui/react-accordion`) and two new files (a hook, a loading component).

**Tech Stack:** FastAPI + SQLAlchemy async + Postgres (backend), React + TypeScript + Vite + TanStack Query + Radix UI + Tailwind (frontend), pytest (backend tests), Vitest + Testing Library + MSW (frontend tests).

## Global Constraints

- `REASONING_CANDIDATE_CAP` changes from `10` to `1` in `src/daad_search/api/query.py`.
- Any LLM `.invoke()` call site that adds `config={"callbacks": [...]}` must not change `get_fallback_llm`'s signature or any function's existing return type.
- `program.structured_eligibility` is already rendered unconditionally in `AdmissionGuideDrawer.tsx` — Feature 1 only adds a heading above it, it does not change when it renders.
- The loading indicator (Feature 7) is frontend-only and purely presentational: no SSE/streaming, no change to `/query`'s request or response shape.
- New frontend dependency: `@radix-ui/react-accordion@^1.2.20` (Feature 2 only).
- TDD throughout, following this repo's existing conventions exactly: pytest with `@pytest.mark.integration` for tests needing Postgres/Qdrant/network, `api_client`/`seeded_session_factory` fixtures from `tests/conftest.py` for API tests; Vitest + Testing Library + MSW (`frontend/src/test/mswServer.ts`) for frontend tests, `npm test` (= `vitest run`) to run them.
- Every step below shows the exact code to write. Read the named file's current content before editing — later tasks in this plan assume earlier tasks' changes are already present.

---

## Task 1: Backend — cap eligibility to 1, add on-demand evaluation endpoint

**Files:**
- Modify: `src/daad_search/api/query.py` (line 16)
- Modify: `src/daad_search/api/main.py`
- Test: `tests/test_query_api.py`

**Interfaces:**
- Produces: `POST /programs/{program_id}/evaluate-eligibility`, request body `{"profile": StudentProfile}`, response `{"eligibility_verdict": ..., "eligibility_reasoning": ...}` — consumed by Task 2's frontend hook.

- [ ] **Step 1: Change the reasoning cap**

In `src/daad_search/api/query.py`, change:

```python
REASONING_CANDIDATE_CAP = 10
```

to:

```python
REASONING_CANDIDATE_CAP = 1
```

- [ ] **Step 2: Write the failing tests for the new endpoint**

Read `tests/test_query_api.py` first — it already defines a `_seed_eligibility(session_factory, program_id, structured_eligibility)` helper and imports `query_module`, `SearchFilters`, `ParsedQuery`, `StudentProfile`. Append to the end of the file:

```python
from daad_search.api import main as main_module
from daad_search.query_understanding.schema import EligibilityVerdict


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_no_data_without_structured_eligibility(api_client):
    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "no_data"
    assert body["eligibility_reasoning"] is None


def test_evaluate_eligibility_returns_404_for_unknown_program(api_client):
    response = api_client.post(
        "/programs/999999/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 404


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_unclear_when_reasoning_fails(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})
    monkeypatch.setattr(main_module, "reason_about_eligibility", lambda profile, candidates: None)

    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "unclear"
    assert body["eligibility_reasoning"] == "Eligibility reasoning was unavailable for this program."


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_real_verdict(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})
    monkeypatch.setattr(
        main_module, "reason_about_eligibility",
        lambda profile, candidates: [EligibilityVerdict(program_id=1, verdict="eligible", reasoning="Meets requirements.")],
    )

    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "eligible"
    assert body["eligibility_reasoning"] == "Meets requirements."
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_query_api.py -k evaluate_eligibility -v`
Expected: FAIL — `404` for all of them, since the route doesn't exist yet (or a collection error on the `main_module`/`EligibilityVerdict` imports if those names aren't yet used — that's fine, it confirms the route is missing).

- [ ] **Step 4: Add the endpoint**

In `src/daad_search/api/main.py`, change the imports at the top from:

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
```

to:

```python
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db.models import Eligibility, Program
from ..db.session import async_session_factory
from ..query_understanding.reasoner import reason_about_eligibility
from ..query_understanding.schema import CandidateForReasoning, QueryRequest, QueryResponse, StudentProfile
from .query import handle_query
from .schemas import ProgramDetail, SearchRequest, SearchResponse
from .search import filtered_search, hybrid_search, to_search_result
```

Then add, after the `get_program` endpoint at the end of the file:

```python
class EvaluateEligibilityRequest(BaseModel):
    profile: StudentProfile


class EvaluateEligibilityResponse(BaseModel):
    eligibility_verdict: Literal["eligible", "likely_eligible", "not_eligible", "unclear", "no_data"]
    eligibility_reasoning: str | None


@app.post("/programs/{program_id}/evaluate-eligibility", response_model=EvaluateEligibilityResponse)
async def evaluate_eligibility(
    program_id: int, request: EvaluateEligibilityRequest, session: AsyncSession = Depends(get_session)
) -> EvaluateEligibilityResponse:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    eligibility = await session.get(Eligibility, program_id)
    if eligibility is None or not eligibility.structured_eligibility:
        return EvaluateEligibilityResponse(eligibility_verdict="no_data", eligibility_reasoning=None)

    candidate = CandidateForReasoning(
        program_id=program_id, course_name=row.course_name,
        structured_eligibility=eligibility.structured_eligibility,
    )
    verdicts = reason_about_eligibility(request.profile, [candidate])
    if not verdicts:
        return EvaluateEligibilityResponse(
            eligibility_verdict="unclear",
            eligibility_reasoning="Eligibility reasoning was unavailable for this program.",
        )
    v = verdicts[0]
    return EvaluateEligibilityResponse(eligibility_verdict=v.verdict, eligibility_reasoning=v.reasoning)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_query_api.py -v`
Expected: all PASS, including the pre-existing tests in this file (confirms the cap change to `1` didn't break `test_query_candidate_with_no_eligibility_row_gets_no_data` and friends — they don't assert on the cap value itself, only per-result verdicts).

- [ ] **Step 6: Commit**

```bash
git add src/daad_search/api/query.py src/daad_search/api/main.py tests/test_query_api.py
git commit -m "feat: cap automatic eligibility reasoning to top 1, add on-demand evaluate-eligibility endpoint"
```

---

## Task 2: Frontend — "Evaluate eligibility" button and admission-requirements heading

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/useEvaluateEligibility.ts`
- Modify: `frontend/src/hooks/hooks.test.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `POST /programs/{program_id}/evaluate-eligibility` from Task 1.
- Produces: `AdmissionGuideDrawer` gains two new required props, `profile: StudentProfile | null` and `onEligibilityEvaluated: (programId: number, verdict: EligibilityVerdictValue, reasoning: string | null) => void` — Task 8 references `App.tsx`'s resulting `resultsForDisplay` variable name.

- [ ] **Step 1: Add the response type**

In `frontend/src/types.ts`, add after the `QueryResponse` interface:

```ts
export interface EvaluateEligibilityResponse {
  eligibility_verdict: EligibilityVerdictValue;
  eligibility_reasoning: string | null;
}
```

- [ ] **Step 2: Add the API client function**

In `frontend/src/api/client.ts`, change the top import from:

```ts
import type { ProgramDetail, QueryResponse, SearchFilters, SearchResponse } from "../types";
```

to:

```ts
import type {
  EvaluateEligibilityResponse, ProgramDetail, QueryResponse, SearchFilters, SearchResponse, StudentProfile,
} from "../types";
```

Then add, after `getProgram`:

```ts
export function postEvaluateEligibility(
  programId: number, profile: StudentProfile,
): Promise<EvaluateEligibilityResponse> {
  return request<EvaluateEligibilityResponse>(`/programs/${programId}/evaluate-eligibility`, {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}
```

- [ ] **Step 3: Write the failing test for the new hook**

Read `frontend/src/hooks/hooks.test.tsx` first. Add to the top imports:

```tsx
import { useEvaluateEligibility } from "./useEvaluateEligibility";
```

Add, after the `useProgramDetail` describe block:

```tsx
describe("useEvaluateEligibility", () => {
  it("posts the profile to the program's evaluate-eligibility endpoint", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/programs/10396/evaluate-eligibility`, async ({ request }) => {
        const body = (await request.json()) as { profile: { nationality: string } };
        expect(body.profile.nationality).toBe("Pakistan");
        return HttpResponse.json({ eligibility_verdict: "eligible", eligibility_reasoning: "Meets requirements." });
      }),
    );
    const { result } = renderHook(() => useEvaluateEligibility(), { wrapper });

    const response = await result.current.mutateAsync({
      programId: 10396, profile: { nationality: "Pakistan" },
    });
    expect(response.eligibility_verdict).toBe("eligible");
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `npm test -- hooks.test.tsx` (from `frontend/`)
Expected: FAIL — `Cannot find module './useEvaluateEligibility'` or similar, since the hook doesn't exist yet.

- [ ] **Step 5: Create the hook**

Create `frontend/src/hooks/useEvaluateEligibility.ts`:

```ts
import { useMutation } from "@tanstack/react-query";

import { postEvaluateEligibility } from "../api/client";
import type { StudentProfile } from "../types";

export function useEvaluateEligibility() {
  return useMutation({
    mutationFn: ({ programId, profile }: { programId: number; profile: StudentProfile }) =>
      postEvaluateEligibility(programId, profile),
  });
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `npm test -- hooks.test.tsx`
Expected: PASS.

- [ ] **Step 7: Rewrite AdmissionGuideDrawer's component**

Read `frontend/src/components/AdmissionGuideDrawer.tsx` first (it currently has no react-query usage). Replace the whole file with:

```tsx
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { useEvaluateEligibility } from "../hooks/useEvaluateEligibility";
import { VERDICT_LABELS, VERDICT_STYLES } from "../lib/verdictDisplay";
import type { EligibilityVerdictValue, ProgramDetail, QueryResult, StudentProfile } from "../types";

interface AdmissionGuideDrawerProps {
  programId: number | null;
  verdict: Pick<QueryResult, "eligibility_verdict" | "eligibility_reasoning"> | null;
  profile: StudentProfile | null;
  program: ProgramDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
  onEligibilityEvaluated: (programId: number, verdict: EligibilityVerdictValue, reasoning: string | null) => void;
}

function hasProfileData(profile: StudentProfile | null): boolean {
  if (!profile) return false;
  return Object.values(profile).some((value) => value !== null && value !== undefined);
}

export function AdmissionGuideDrawer({
  programId, verdict, profile, program, isLoading, isError, onClose, onEligibilityEvaluated,
}: AdmissionGuideDrawerProps) {
  const evaluateEligibility = useEvaluateEligibility();

  function handleEvaluate() {
    if (programId === null || !profile) return;
    evaluateEligibility.mutate(
      { programId, profile },
      {
        onSuccess: (response) => {
          onEligibilityEvaluated(programId, response.eligibility_verdict, response.eligibility_reasoning);
        },
      },
    );
  }

  return (
    <Dialog.Root open={programId !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-background p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold">Admission guide</Dialog.Title>
            <Dialog.Close aria-label="Close" className="text-ink/40 hover:text-ink">
              <X size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Eligibility and admission requirements for this program.
          </Dialog.Description>

          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-ink/70">Loading...</p>}

          {!isLoading && !isError && program && (
            <div className="space-y-4">
              <a
                href={program.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-accent hover:underline"
              >
                View program page ↗
              </a>

              {verdict && (
                <div>
                  <h3 className="text-sm font-medium text-ink">Eligibility</h3>
                  <span
                    className={`mt-1 inline-flex rounded-full px-2 py-1 text-xs font-medium ${VERDICT_STYLES[verdict.eligibility_verdict]}`}
                  >
                    {VERDICT_LABELS[verdict.eligibility_verdict]}
                  </span>
                  {verdict.eligibility_verdict === "no_data" && hasProfileData(profile) ? (
                    <div className="mt-1">
                      <button
                        type="button"
                        onClick={handleEvaluate}
                        disabled={evaluateEligibility.isPending}
                        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {evaluateEligibility.isPending ? "Evaluating..." : "Evaluate eligibility"}
                      </button>
                    </div>
                  ) : verdict.eligibility_verdict === "no_data" ? (
                    <p className="mt-1 text-sm text-ink/70">Add your background to the search box to check eligibility</p>
                  ) : (
                    <p className="mt-1 text-sm text-ink/70">{verdict.eligibility_reasoning ?? "No reasoning available."}</p>
                  )}
                </div>
              )}

              {program.structured_eligibility && (
                <div>
                  <h3 className="text-sm font-medium text-ink">Admission Requirements</h3>
                  <div className="mt-1">
                    <StructuredAdmissionGuide eligibility={program.structured_eligibility} />
                  </div>
                </div>
              )}

              <div>
                <h3 className="text-sm font-medium text-ink">Original program details</h3>
                <div className="mt-1">
                  <RawAdmissionText rawSections={program.raw_sections} />
                </div>
              </div>
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
      {(eligibility.language_requirements ?? []).map((req, index) => (
        <RequirementRow
          key={`${req.language}-${index}`}
          label={`${req.language}: ${req.level ?? "No minimum level required"}`}
          quote={req.source_quote}
        />
      ))}
      {(eligibility.standardized_tests ?? []).map((test, index) => (
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
    <div className="rounded-lg border border-line p-3">
      <p className="text-sm font-medium text-ink">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-ink/70">"{quote}"</p>}
    </div>
  );
}

function RawAdmissionText({ rawSections }: { rawSections: Record<string, string> }) {
  const sections = Object.entries(rawSections).filter(([, text]) => text);
  if (sections.length === 0) {
    return <p className="text-sm text-ink/70">No admission text available for this program.</p>;
  }
  return (
    <div className="space-y-3">
      {sections.map(([key, text]) => (
        <div key={key}>
          <h4 className="text-xs font-medium uppercase text-ink/40">{key.replace(/_/g, " ")}</h4>
          <p className="text-sm text-ink/80">{text}</p>
        </div>
      ))}
    </div>
  );
}
```

(`RequirementRow` and `RawAdmissionText` are unchanged here — Task 3 rewrites `RawAdmissionText` and Task 5 rewrites `RequirementRow`. This step's only real changes are: the two new props, `hasProfileData`, the button/message branch, the `useEvaluateEligibility` hook call, and the new "Admission Requirements" heading.)

- [ ] **Step 8: Rewrite AdmissionGuideDrawer's test file**

Every existing test renders `<AdmissionGuideDrawer>` directly with no `QueryClientProvider` — that stops working now that the component uses `useMutation` internally. Replace the whole file with:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { mswServer } from "../test/mswServer";
import type { ProgramDetail } from "../types";
import { AdmissionGuideDrawer } from "./AdmissionGuideDrawer";

const API_BASE_URL = "http://localhost:8000";

const BASE_PROGRAM: ProgramDetail = {
  id: 10396, course_name: "Additive Manufacturing", university: "TU X", city: null, languages: ["English"],
  subject: null, tuition_fees_text: null, application_deadline_text: null, link: "https://example.com", score: null,
  course_type: 2, degree: null, duration: null, beginning: null, raw_sections: {}, structured_eligibility: null,
};

function renderDrawer(props: Partial<ComponentProps<typeof AdmissionGuideDrawer>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const defaults: ComponentProps<typeof AdmissionGuideDrawer> = {
    programId: 10396, verdict: null, profile: null, program: BASE_PROGRAM,
    isLoading: false, isError: false, onClose: vi.fn(), onEligibilityEvaluated: vi.fn(),
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <AdmissionGuideDrawer {...defaults} {...props} />
    </QueryClientProvider>,
  );
}

describe("AdmissionGuideDrawer", () => {
  it("renders nothing (closed) when programId is null", () => {
    renderDrawer({ programId: null, program: undefined });
    expect(screen.queryByText("Admission guide")).not.toBeInTheDocument();
  });

  it("renders a link to the program's DAAD page", () => {
    renderDrawer({ program: { ...BASE_PROGRAM, link: "https://www2.daad.de/program/10396" } });
    const link = screen.getByRole("link", { name: /view program page/i });
    expect(link).toHaveAttribute("href", "https://www2.daad.de/program/10396");
  });

  it("shows the loading state", () => {
    renderDrawer({ program: undefined, isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows the error state", () => {
    renderDrawer({ program: undefined, isError: true });
    expect(screen.getByText(/couldn't load this program/i)).toBeInTheDocument();
  });

  it("falls back to raw_sections when structured_eligibility is null", () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." } },
    });
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });

  it("renders the verdict badge and reasoning when a real verdict is provided", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "eligible", eligibility_reasoning: "Meets the grade threshold." },
    });
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByText(/meets the grade threshold/i)).toBeInTheDocument();
  });

  it("renders a null language level as 'no minimum level required', not the literal word null", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: null,
          extraction_confidence: "high", degree_prerequisite: null, grade_requirement: null,
          standardized_tests: [],
          language_requirements: [
            { language: "German", level: null, accepted_tests: [], source_quote: "No minimum language level required" },
          ],
          notes: null,
        },
      },
    });
    expect(screen.getByText(/german: no minimum level required/i)).toBeInTheDocument();
    expect(screen.queryByText(/german: null/i)).not.toBeInTheDocument();
  });

  it("shows the original raw program details alongside the structured summary, not instead of it", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." },
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: "B2",
          extraction_confidence: "high", degree_prerequisite: null,
          grade_requirement: { value: 2.5, scale: "German grading scale", source_quote: "A grade of 2.5 or better is required." },
          standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getByText(/grade requirement: 2.5/i)).toBeInTheDocument();
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });

  it("renders structured requirements with their source quotes, under an Admission Requirements heading", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: "B2",
          extraction_confidence: "high", degree_prerequisite: null,
          grade_requirement: { value: 2.5, scale: "German grading scale", source_quote: "A grade of 2.5 or better is required." },
          standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getByText("Admission Requirements")).toBeInTheDocument();
    expect(screen.getByText(/grade requirement: 2.5/i)).toBeInTheDocument();
    expect(screen.getByText(/a grade of 2.5 or better is required/i)).toBeInTheDocument();
  });

  it("shows an 'Evaluate eligibility' button when the verdict is no_data and a profile exists", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: { nationality: "Pakistan" },
    });
    expect(screen.getByRole("button", { name: /evaluate eligibility/i })).toBeInTheDocument();
  });

  it("shows a prompt to add background instead of a button when the verdict is no_data and there is no profile", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: null,
    });
    expect(screen.queryByRole("button", { name: /evaluate eligibility/i })).not.toBeInTheDocument();
    expect(screen.getByText(/add your background to the search box to check eligibility/i)).toBeInTheDocument();
  });

  it("clicking 'Evaluate eligibility' calls the endpoint and reports the result via onEligibilityEvaluated", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/programs/10396/evaluate-eligibility`, () =>
        HttpResponse.json({ eligibility_verdict: "eligible", eligibility_reasoning: "Meets all requirements." }),
      ),
    );
    const onEligibilityEvaluated = vi.fn();
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: { nationality: "Pakistan" },
      onEligibilityEvaluated,
    });

    await userEvent.click(screen.getByRole("button", { name: /evaluate eligibility/i }));

    await waitFor(() =>
      expect(onEligibilityEvaluated).toHaveBeenCalledWith(10396, "eligible", "Meets all requirements."),
    );
  });
});
```

- [ ] **Step 9: Run the drawer tests to verify they pass**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: all PASS.

- [ ] **Step 10: Wire the new props into App.tsx and fix the verdict-update propagation**

Read `frontend/src/App.tsx` first. Replace the whole file with:

```tsx
import { useMemo, useState } from "react";

import { AdmissionGuideDrawer } from "./components/AdmissionGuideDrawer";
import { ChatQueryBox } from "./components/ChatQueryBox";
import { ExtractionSummary } from "./components/ExtractionSummary";
import { Header } from "./components/Header";
import { Pagination } from "./components/Pagination";
import { ResultsList } from "./components/ResultsList";
import { useFilteredSearch } from "./hooks/useFilteredSearch";
import { useProgramDetail } from "./hooks/useProgramDetail";
import { useQuerySearch } from "./hooks/useQuerySearch";
import { buildVerdictMap, mergeVerdicts, type VerdictInfo } from "./lib/mergeVerdicts";
import type { EligibilityVerdictValue, QueryResponse, QueryResult, SearchFilters } from "./types";

const PAGE_SIZE = 20;

type ActiveQuery =
  | { type: "query"; query: string }
  | { type: "filters"; filters: SearchFilters; semanticQuery: string | null };

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
  const [activeQuery, setActiveQuery] = useState<ActiveQuery | null>(null);
  const [offset, setOffset] = useState(0);
  const [totalMatched, setTotalMatched] = useState(0);

  const querySearch = useQuerySearch();
  const filteredSearch = useFilteredSearch();
  const programDetail = useProgramDetail(selectedProgramId);

  const resultsForDisplay = useMemo(
    () => mergeVerdicts(displayedResults, verdictMap),
    [displayedResults, verdictMap],
  );

  function runQuerySearch(query: string, offset: number) {
    setActiveQuery({ type: "query", query });
    querySearch.mutate(
      { query, offset },
      {
        onSuccess: (response) => {
          setQueryResponse(response);
          setDisplayedResults(response.results);
          setActiveFilters(response.extracted_filters);
          setVerdictMap(buildVerdictMap(response.results));
          setTotalMatched(response.total_matched);
        },
      },
    );
  }

  function runFilteredSearch(filters: SearchFilters, semanticQuery: string | null, offset: number) {
    const previousFilters = activeFilters;
    const previousActiveQuery = activeQuery;
    setActiveFilters(filters);
    setActiveQuery({ type: "filters", filters, semanticQuery });
    filteredSearch.mutate(
      { filters, semanticQuery, offset },
      {
        onSuccess: (response) => {
          setDisplayedResults(response.results);
          setTotalMatched(response.total_matched);
        },
        onError: () => {
          setActiveFilters(previousFilters);
          setActiveQuery(previousActiveQuery);
        },
      },
    );
  }

  function handleSubmit(query: string) {
    setOffset(0);
    runQuerySearch(query, 0);
  }

  function handleFiltersChange(filters: SearchFilters) {
    setOffset(0);
    runFilteredSearch(filters, queryResponse?.semantic_query ?? null, 0);
  }

  function handlePageChange(newOffset: number) {
    if (!activeQuery) return;
    setOffset(newOffset);
    if (activeQuery.type === "query") {
      runQuerySearch(activeQuery.query, newOffset);
    } else {
      runFilteredSearch(activeQuery.filters, activeQuery.semanticQuery, newOffset);
    }
  }

  function handleStartOver() {
    setQueryResponse(null);
    setDisplayedResults([]);
    setActiveFilters(null);
    setVerdictMap(new Map());
    setSelectedProgramId(null);
    setActiveQuery(null);
    setOffset(0);
    setTotalMatched(0);
    querySearch.reset();
    filteredSearch.reset();
  }

  function handleEligibilityEvaluated(
    programId: number, verdict: EligibilityVerdictValue, reasoning: string | null,
  ) {
    setVerdictMap((previous) => {
      const next = new Map(previous);
      next.set(programId, { verdict, reasoning });
      return next;
    });
  }

  const hasSubmitted = querySearch.isPending || queryResponse !== null;
  const selectedVerdictInfo = selectedProgramId !== null ? verdictMap.get(selectedProgramId) : undefined;
  const selectedVerdict = selectedVerdictInfo
    ? { eligibility_verdict: selectedVerdictInfo.verdict, eligibility_reasoning: selectedVerdictInfo.reasoning }
    : null;

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <Header />
      <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />

      {querySearch.isError && (
        <ErrorBanner
          onRetry={() =>
            querySearch.variables !== undefined &&
            runQuerySearch(querySearch.variables.query, querySearch.variables.offset)
          }
        />
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
                className="shrink-0 text-sm text-ink/40 hover:text-ink"
              >
                Start over
              </button>
            </div>
          )}

          {filteredSearch.isError && (
            <ErrorBanner
              onRetry={() =>
                filteredSearch.variables !== undefined &&
                runFilteredSearch(
                  filteredSearch.variables.filters,
                  filteredSearch.variables.semanticQuery,
                  filteredSearch.variables.offset,
                )
              }
            />
          )}

          <ResultsList
            results={resultsForDisplay}
            isLoading={querySearch.isPending || filteredSearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />

          <Pagination offset={offset} limit={PAGE_SIZE} total={totalMatched} onPageChange={handlePageChange} />
        </>
      )}

      <AdmissionGuideDrawer
        programId={selectedProgramId}
        verdict={selectedVerdict}
        profile={queryResponse?.extracted_profile ?? null}
        program={programDetail.data}
        isLoading={programDetail.isLoading}
        isError={programDetail.isError}
        onClose={() => setSelectedProgramId(null)}
        onEligibilityEvaluated={handleEligibilityEvaluated}
      />
    </main>
  );
}
```

Note what changed from the previous version: `runFilteredSearch`'s `onSuccess` now sets `displayedResults` to the raw `response.results` instead of pre-merging with `mergeVerdicts` — the new `resultsForDisplay` memo does that merge at render time for both paths, from a single source of truth (`verdictMap`), so a click on "Evaluate eligibility" updates the drawer and the results-list card from the one `setVerdictMap` call in `handleEligibilityEvaluated`.

- [ ] **Step 11: Run the full frontend test suite**

Run: `npm test` (from `frontend/`)
Expected: all PASS, including `App.test.tsx` (its existing assertions about eligibility badges after a filter-chip removal still hold, since `resultsForDisplay` reproduces the same merge `runFilteredSearch` used to do inline).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts frontend/src/hooks/useEvaluateEligibility.ts \
  frontend/src/hooks/hooks.test.tsx frontend/src/components/AdmissionGuideDrawer.tsx \
  frontend/src/components/AdmissionGuideDrawer.test.tsx frontend/src/App.tsx
git commit -m "feat: on-demand eligibility evaluation button, Admission Requirements heading"
```

---

## Task 3: Frontend — organized dropdowns for original program details

**Files:**
- Modify: `frontend/package.json` (new dependency)
- Modify: `frontend/src/components/AdmissionGuideDrawer.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.test.tsx`

**Interfaces:**
- Consumes: `ProgramDetail.raw_sections` keys, confirmed exact set: `description`, `degree`, `tuition_fees`, `application_deadline`, `admission_requirements`, `german_language`, `english_language` (from `src/daad_search/scraping/detail_parser.py`'s `_LABEL_TO_KEY`) — no other keys exist.

- [ ] **Step 1: Install the Accordion package**

```bash
cd frontend && npm install @radix-ui/react-accordion@^1.2.20
```

- [ ] **Step 2: Write the failing tests**

Read `frontend/src/components/AdmissionGuideDrawer.test.tsx` first (as left by Task 2). Two existing tests assert raw-section text is visible without opening anything — that stops being true once sections start closed by default. Change:

```tsx
  it("falls back to raw_sections when structured_eligibility is null", () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." } },
    });
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });
```

to:

```tsx
  it("falls back to raw_sections when structured_eligibility is null", async () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." } },
    });
    await userEvent.click(screen.getByRole("button", { name: /requirements & language/i }));
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });
```

And change:

```tsx
  it("shows the original raw program details alongside the structured summary, not instead of it", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." },
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: "B2",
          extraction_confidence: "high", degree_prerequisite: null,
          grade_requirement: { value: 2.5, scale: "German grading scale", source_quote: "A grade of 2.5 or better is required." },
          standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getByText(/grade requirement: 2.5/i)).toBeInTheDocument();
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });
```

to:

```tsx
  it("shows the original raw program details alongside the structured summary, not instead of it", async () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." },
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: "B2",
          extraction_confidence: "high", degree_prerequisite: null,
          grade_requirement: { value: 2.5, scale: "German grading scale", source_quote: "A grade of 2.5 or better is required." },
          standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getByText(/grade requirement: 2.5/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /requirements & language/i }));
    expect(screen.getByText(/a bachelor's degree with a grade of 2.5 or better/i)).toBeInTheDocument();
  });
```

Then add these new tests at the end of the `describe` block, before the closing `});`:

```tsx
  it("only shows sections that have at least one non-empty field", () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { description: "A great program.", degree: "Master of Science" } },
    });
    expect(screen.getByRole("button", { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /course details/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /costs & deadlines/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /requirements & language/i })).not.toBeInTheDocument();
  });

  it("groups tuition fees and application deadline under Costs & Deadlines", async () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { tuition_fees: "No tuition fees.", application_deadline: "15 July" } },
    });
    await userEvent.click(screen.getByRole("button", { name: /costs & deadlines/i }));
    expect(screen.getByText("No tuition fees.")).toBeInTheDocument();
    expect(screen.getByText("15 July")).toBeInTheDocument();
  });

  it("shows the 'no admission text available' message when raw_sections is empty", () => {
    renderDrawer({ program: { ...BASE_PROGRAM, raw_sections: {} } });
    expect(screen.getByText(/no admission text available/i)).toBeInTheDocument();
  });

  it("shows the 'Original program details' heading more prominently than a plain label", () => {
    renderDrawer({ program: { ...BASE_PROGRAM, raw_sections: { description: "A great program." } } });
    expect(screen.getByText("Original program details").className).toContain("font-semibold");
  });
```

- [ ] **Step 3: Run the tests to verify the new/changed ones fail**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: FAIL on the sections/heading tests (accordion doesn't exist yet, heading isn't bold yet); the two changed tests fail because there's no button named "Requirements & Language" yet.

- [ ] **Step 4: Rewrite `RawAdmissionText` and the "Original program details" heading**

In `frontend/src/components/AdmissionGuideDrawer.tsx`, add to the top imports:

```tsx
import * as Accordion from "@radix-ui/react-accordion";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, X } from "lucide-react";
```

(replacing the existing `import * as Dialog from "@radix-ui/react-dialog";` and `import { X } from "lucide-react";` lines).

Change the "Original program details" heading from:

```tsx
              <div>
                <h3 className="text-sm font-medium text-ink">Original program details</h3>
                <div className="mt-1">
                  <RawAdmissionText rawSections={program.raw_sections} />
                </div>
              </div>
```

to:

```tsx
              <div>
                <h3 className="text-base font-semibold text-ink">Original program details</h3>
                <div className="mt-2">
                  <RawAdmissionText rawSections={program.raw_sections} />
                </div>
              </div>
```

Replace the `RawAdmissionText` function (currently a flat `Object.entries` dump) with:

```tsx
interface RawSectionField {
  key: string;
  label: string;
}

interface RawSectionGroup {
  key: string;
  title: string;
  fields: RawSectionField[];
}

const RAW_SECTION_GROUPS: RawSectionGroup[] = [
  { key: "overview", title: "Overview", fields: [{ key: "description", label: "Description" }] },
  { key: "course-details", title: "Course Details", fields: [{ key: "degree", label: "Degree" }] },
  {
    key: "costs-deadlines", title: "Costs & Deadlines",
    fields: [
      { key: "tuition_fees", label: "Tuition Fees" },
      { key: "application_deadline", label: "Application Deadline" },
    ],
  },
  {
    key: "requirements-language", title: "Requirements & Language",
    fields: [
      { key: "admission_requirements", label: "Admission Requirements" },
      { key: "german_language", label: "German Language" },
      { key: "english_language", label: "English Language" },
    ],
  },
];

function RawAdmissionText({ rawSections }: { rawSections: Record<string, string> }) {
  const groups = RAW_SECTION_GROUPS.map((group) => ({
    ...group,
    fields: group.fields.filter((field) => rawSections[field.key]),
  })).filter((group) => group.fields.length > 0);

  if (groups.length === 0) {
    return <p className="text-sm text-ink/70">No admission text available for this program.</p>;
  }

  return (
    <Accordion.Root type="multiple" className="space-y-2">
      {groups.map((group) => (
        <Accordion.Item key={group.key} value={group.key} className="rounded-lg border border-line">
          <Accordion.Header>
            <Accordion.Trigger className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-ink">
              {group.title}
              <ChevronDown size={16} className="text-ink/40 transition-transform data-[state=open]:rotate-180" />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Content className="space-y-3 px-3 pb-3">
            {group.fields.map((field) => (
              <div key={field.key}>
                <h4 className="text-xs font-medium uppercase text-ink/40">{field.label}</h4>
                <p className="text-sm text-ink/80">{rawSections[field.key]}</p>
              </div>
            ))}
          </Accordion.Content>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS (checks `App.test.tsx`'s use of `raw_sections: { admission_requirements: "..." }` still resolves — that test only asserts the drawer opens and shows the *structured* eligibility reasoning and requirement row, not the raw section text, so it's unaffected by sections now starting closed).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/AdmissionGuideDrawer.tsx \
  frontend/src/components/AdmissionGuideDrawer.test.tsx
git commit -m "feat: organize original program details into collapsible sections"
```

---

## Task 4: Frontend — pre-filled query template and degree-level example chips

**Files:**
- Modify: `frontend/src/components/ChatQueryBox.tsx`
- Modify: `frontend/src/components/ChatQueryBox.test.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing tests for ChatQueryBox**

Replace `frontend/src/components/ChatQueryBox.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatQueryBox } from "./ChatQueryBox";

describe("ChatQueryBox", () => {
  it("pre-fills the textarea with the Master's template on load", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[Master's]");
  });

  it("calls onSubmit with the trimmed query text", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "  bachelors in AI, CGPA 3.2  ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalledWith("bachelors in AI, CGPA 3.2");
  });

  it("does not call onSubmit for empty or whitespace-only input", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "   ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows loading copy while pending", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={true} />);
    expect(screen.getByRole("button", { name: /reading your profile/i })).toBeDisabled();
  });

  it("clicking the PhD example chip replaces the textarea content with the PhD template", async () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByRole("button", { name: /phd example/i }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[PhD]");
  });

  it("clicking the Bachelor's example chip replaces the textarea content with the Bachelor's template", async () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByRole("button", { name: /bachelor's example/i }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[Bachelor's]");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: FAIL — textarea starts empty, no example chips exist yet.

- [ ] **Step 3: Rewrite ChatQueryBox**

Replace `frontend/src/components/ChatQueryBox.tsx` with:

```tsx
import { type FormEvent, useState } from "react";

const MASTERS_TEMPLATE = `I am looking for a [Master's] program in [AI, agentic AI, and large language models], taught in [English], with [no tuition fees], near [Berlin].

I have a [Bachelor's degree in Computer Science] with a [3.2 GPA on a 4.0 scale] from [Pakistan], and an [IELTS score of 7.0].`;

const PHD_TEMPLATE = `I am looking for a [PhD] position in [machine learning and natural language processing], taught in [English], with [no tuition fees], near [Munich].

I have a [Master's degree in Computer Science] with a [1.7 grade on the German scale] from [Nigeria], [2 years of research experience in NLP], and an [IELTS score of 7.5].`;

const BACHELORS_TEMPLATE = `I am looking for a [Bachelor's] program in [computer science or data science], taught in [English], with [no tuition fees], near [Hamburg].

I completed [high school / Abitur-equivalent] with a [grade of 85%] in [India], and an [IELTS score of 6.5].`;

interface ChatQueryBoxProps {
  onSubmit: (query: string) => void;
  isPending: boolean;
}

export function ChatQueryBox({ onSubmit, isPending }: ChatQueryBoxProps) {
  const [query, setQuery] = useState(MASTERS_TEMPLATE);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-2xl border border-line bg-background p-4 shadow-sm"
    >
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        rows={5}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setQuery(PHD_TEMPLATE)}
          className="rounded-full border border-line px-3 py-1 text-xs text-ink/70 hover:bg-line/40"
        >
          PhD example
        </button>
        <button
          type="button"
          onClick={() => setQuery(BACHELORS_TEMPLATE)}
          className="rounded-full border border-line px-3 py-1 text-xs text-ink/70 hover:bg-line/40"
        >
          Bachelor's example
        </button>
      </div>
      <button
        type="submit"
        disabled={isPending || query.trim().length === 0}
        className="self-end rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isPending ? "Reading your profile and checking eligibility..." : "Search programs"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run the ChatQueryBox tests to verify they pass**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Fix App.test.tsx's now-broken placeholder lookups**

Read `frontend/src/App.test.tsx` first. It has 4 occurrences of this pattern (one in each of 4 tests: "submits a query...", "pages through results...", "retry after a failed query...", "start over resets..."):

```tsx
    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters, English taught");
```

(the exact query text passed to `userEvent.type` differs per test — `"robotics masters, English taught"` in the first, `"robotics masters"` in the other three). The textarea no longer has a placeholder (it's pre-filled with real template text instead), and typing into a non-empty field would append rather than replace. Change each of the 4 occurrences from this shape:

```tsx
    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "SOME QUERY TEXT");
```

to this shape, keeping each test's original query text:

```tsx
    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "SOME QUERY TEXT");
```

- [ ] **Step 6: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ChatQueryBox.tsx frontend/src/components/ChatQueryBox.test.tsx frontend/src/App.test.tsx
git commit -m "feat: pre-filled query template with PhD/Bachelor's example chips"
```

---

## Task 5: Frontend — stop rendering duplicate requirement text

**Files:**
- Modify: `frontend/src/components/AdmissionGuideDrawer.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/components/AdmissionGuideDrawer.test.tsx`, at the end of the `describe` block:

```tsx
  it("omits the quote block in a requirement row when the quote is identical to the label", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: null,
          extraction_confidence: "high",
          degree_prerequisite: {
            description: "A relevant bachelor's degree is required.",
            source_quote: "A relevant bachelor's degree is required.",
          },
          grade_requirement: null, standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getAllByText(/a relevant bachelor's degree is required/i)).toHaveLength(1);
  });

  it("still shows the quote in a requirement row when it differs from the label", () => {
    renderDrawer({
      program: {
        ...BASE_PROGRAM,
        structured_eligibility: {
          requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: null,
          extraction_confidence: "high",
          degree_prerequisite: {
            description: "A relevant bachelor's degree is required.",
            source_quote: "Applicants must hold a bachelor's degree in a related field.",
          },
          grade_requirement: null, standardized_tests: [], language_requirements: [], notes: null,
        },
      },
    });
    expect(screen.getByText(/a relevant bachelor's degree is required/i)).toBeInTheDocument();
    expect(screen.getByText(/applicants must hold a bachelor's degree in a related field/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests to verify the first one fails**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: FAIL on "omits the quote block..." (both the label and the identical quote currently render, so `getAllByText` finds 2 matches, not 1).

- [ ] **Step 3: Fix `RequirementRow`**

In `frontend/src/components/AdmissionGuideDrawer.tsx`, change:

```tsx
function RequirementRow({ label, quote }: { label: string; quote: string | null }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-sm font-medium text-ink">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-ink/70">"{quote}"</p>}
    </div>
  );
}
```

to:

```tsx
function RequirementRow({ label, quote }: { label: string; quote: string | null }) {
  const showQuote = quote && quote.trim() !== label.trim();
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-sm font-medium text-ink">{label}</p>
      {showQuote && <p className="mt-1 text-xs italic text-ink/70">"{quote}"</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AdmissionGuideDrawer.tsx frontend/src/components/AdmissionGuideDrawer.test.tsx
git commit -m "fix: stop rendering an identical source quote under a requirement label"
```

---

## Task 6: German grade-scale equivalent (backend + frontend)

**Files:**
- Modify: `src/daad_search/query_understanding/schema.py`
- Modify: `src/daad_search/api/query.py`
- Modify: `tests/test_query_api.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/ExtractionSummary.tsx`
- Modify: `frontend/src/components/ExtractionSummary.test.tsx`

- [ ] **Step 1: Write the failing backend tests**

Append to `tests/test_query_api.py`:

```python
@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_populates_german_scale_grade_conversion(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(), semantic_query=None,
            student_profile=StudentProfile(grade_value=2.0, grade_scale="4.0 GPA scale (USA)"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_profile"]["grade_value_on_german_scale"] == pytest.approx(3.0)


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_leaves_german_scale_conversion_null_for_unrecognized_scale(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(), semantic_query=None,
            student_profile=StudentProfile(grade_value=7.5, grade_scale="some obscure national scale"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_profile"]["grade_value_on_german_scale"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_query_api.py -k german_scale -v`
Expected: FAIL — `KeyError`/`None` mismatch, since `extracted_profile` has no `grade_value_on_german_scale` key yet (pydantic just omits/nulls unknown behavior; the field doesn't exist so the value won't be `3.0`).

- [ ] **Step 3: Add the field to `StudentProfile`**

In `src/daad_search/query_understanding/schema.py`, change:

```python
class StudentProfile(BaseModel):
    degree_field: str | None = None
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    other_notes: str | None = None
```

to:

```python
class StudentProfile(BaseModel):
    degree_field: str | None = None
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    other_notes: str | None = None
    grade_value_on_german_scale: float | None = None
```

- [ ] **Step 4: Populate it in `handle_query`**

In `src/daad_search/api/query.py`, change the reasoner import line from:

```python
from ..query_understanding.reasoner import reason_about_eligibility
```

to:

```python
from ..query_understanding.reasoner import convert_to_german_scale, reason_about_eligibility
```

Then, right after the `if/else` block that sets `filters`/`semantic_query`/`profile` (i.e. right after the line `profile = None` in the `else` branch, before `if semantic_query:`), add:

```python

    if profile is not None and profile.grade_value is not None:
        profile.grade_value_on_german_scale = convert_to_german_scale(profile.grade_value, profile.grade_scale)
```

- [ ] **Step 5: Run the backend tests to verify they pass**

Run: `pytest tests/test_query_api.py -v`
Expected: all PASS.

- [ ] **Step 6: Write the failing frontend test**

In `frontend/src/components/ExtractionSummary.test.tsx`, add to the `describe` block:

```tsx
  it("shows the German-scale equivalent in brackets when the backend provides one", () => {
    render(
      <ExtractionSummary
        filters={{ languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={{
          degree_field: null, grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)",
          nationality: null, other_notes: null, grade_value_on_german_scale: 1.7,
        }}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Grade: 3.2 (4.0 GPA scale (USA)) [≈ 1.7 German scale]")).toBeInTheDocument();
  });
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `npm test -- ExtractionSummary.test.tsx`
Expected: FAIL — chip text doesn't include the bracketed conversion yet.

- [ ] **Step 8: Add the field to the frontend type and render it**

In `frontend/src/types.ts`, change:

```ts
export interface StudentProfile {
  degree_field?: string | null;
  grade_value?: number | null;
  grade_scale?: string | null;
  nationality?: string | null;
  other_notes?: string | null;
}
```

to:

```ts
export interface StudentProfile {
  degree_field?: string | null;
  grade_value?: number | null;
  grade_scale?: string | null;
  nationality?: string | null;
  other_notes?: string | null;
  grade_value_on_german_scale?: number | null;
}
```

In `frontend/src/components/ExtractionSummary.tsx`, change:

```ts
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
```

to:

```ts
function buildProfileChips(profile: StudentProfile): string[] {
  const chips: string[] = [];
  if (profile.degree_field) chips.push(`Degree: ${profile.degree_field}`);
  if (profile.grade_value != null) {
    const scaleSuffix = profile.grade_scale ? ` (${profile.grade_scale})` : "";
    const germanSuffix = profile.grade_value_on_german_scale != null
      ? ` [≈ ${profile.grade_value_on_german_scale} German scale]`
      : "";
    chips.push(`Grade: ${profile.grade_value}${scaleSuffix}${germanSuffix}`);
  }
  if (profile.nationality) chips.push(`Nationality: ${profile.nationality}`);
  if (profile.other_notes) chips.push(profile.other_notes);
  return chips;
}
```

- [ ] **Step 9: Run the frontend tests to verify they pass**

Run: `npm test -- ExtractionSummary.test.tsx`
Expected: all PASS, including the pre-existing "renders profile fields as read-only chips" test (its profile object has no `grade_value_on_german_scale` field, so it stays `undefined`, `!= null` is false, and the chip text stays exactly `"Grade: 3.2 (4.0 GPA scale (USA))"` as before).

- [ ] **Step 10: Run both full test suites**

Run: `pytest -m "not integration"` (from repo root) and `npm test` (from `frontend/`)
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add src/daad_search/query_understanding/schema.py src/daad_search/api/query.py tests/test_query_api.py \
  frontend/src/types.ts frontend/src/components/ExtractionSummary.tsx frontend/src/components/ExtractionSummary.test.tsx
git commit -m "feat: surface the German-scale grade equivalent already computed by the backend"
```

---

## Task 7: Backend — structured logging & observability

**Files:**
- Modify: `src/daad_search/api/main.py`
- Modify: `src/daad_search/query_understanding/llm.py`
- Modify: `src/daad_search/query_understanding/parser.py`
- Modify: `src/daad_search/query_understanding/reasoner.py`
- Modify: `src/daad_search/api/query.py`
- Modify: `tests/test_query_understanding_llm.py`
- Modify: `tests/test_query_parser.py`
- Modify: `tests/test_eligibility_reasoner.py`
- Modify: `tests/test_query_api.py`

**Interfaces:**
- Produces: `ModelNameCapture` (`src/daad_search/query_understanding/llm.py`) — a `BaseCallbackHandler` subclass with a `.model_name: str | None` attribute, set after `.on_llm_end(...)` runs.

- [ ] **Step 1: Two existing test fakes will break under a `config=` kwarg — fix them first**

Both `tests/test_query_parser.py` and `tests/test_eligibility_reasoner.py` monkeypatch `get_fallback_llm` with a hand-written fake chain whose `invoke` only accepts `(self, prompt)`. Once `parse_query`/`reason_about_eligibility` start calling `.invoke(prompt, config=...)` (Step 4/5 below), these fakes need `config` accepted.

In `tests/test_query_parser.py`, change:

```python
    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")
```

to:

```python
    class AlwaysFailsChain:
        def invoke(self, prompt, config=None):
            raise RuntimeError("all providers exhausted")
```

In `tests/test_eligibility_reasoner.py`, change:

```python
    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")
```

to:

```python
    class AlwaysFailsChain:
        def invoke(self, prompt, config=None):
            raise RuntimeError("all providers exhausted")
```

- [ ] **Step 2: Write the failing test for `ModelNameCapture`**

Create `tests/test_llm_observability.py`:

```python
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from daad_search.query_understanding.llm import ModelNameCapture


def test_model_name_capture_extracts_model_name_from_response_metadata():
    capture = ModelNameCapture()
    message = AIMessage(content="", response_metadata={"model_name": "llama-3.3-70b-versatile"})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])

    capture.on_llm_end(result)

    assert capture.model_name == "llama-3.3-70b-versatile"


def test_model_name_capture_stays_none_when_generations_are_empty():
    capture = ModelNameCapture()
    result = LLMResult(generations=[])

    capture.on_llm_end(result)

    assert capture.model_name is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_llm_observability.py -v`
Expected: FAIL — `ImportError: cannot import name 'ModelNameCapture'`.

- [ ] **Step 4: Add `ModelNameCapture` to `llm.py`**

In `src/daad_search/query_understanding/llm.py`, add to the top imports:

```python
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
```

and add, after the module-level constants (`GROQ_MODEL`, `MISTRAL_MODEL`, `GEMINI_MODEL`) and before `T = TypeVar(...)`:

```python
class ModelNameCapture(BaseCallbackHandler):
    """Records which provider answered a `.invoke()` call, via LangChain's
    on_llm_end callback. Read `.model_name` after the invoke returns."""

    def __init__(self) -> None:
        self.model_name: str | None = None

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        try:
            message = response.generations[0][0].message
            metadata = message.response_metadata
        except (IndexError, AttributeError):
            return
        self.model_name = metadata.get("model_name") or metadata.get("model")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_llm_observability.py -v`
Expected: PASS.

- [ ] **Step 6: Run the existing LLM fallback-chain tests to confirm no regression**

Run: `pytest tests/test_query_understanding_llm.py -v`
Expected: all PASS unchanged — `ModelNameCapture` is additive, `get_fallback_llm` itself isn't touched.

- [ ] **Step 7: Write the failing caplog test for `parse_query`**

In `tests/test_query_parser.py`, add to the top imports:

```python
import logging

from daad_search.api.schemas import SearchFilters
from daad_search.query_understanding.schema import ParsedQuery, StudentProfile
```

and add this test:

```python
def test_parse_query_logs_the_raw_query_filters_and_profile(monkeypatch, caplog):
    from daad_search.query_understanding import parser as parser_module

    class FakeChain:
        def invoke(self, prompt, config=None):
            return ParsedQuery(
                filters=SearchFilters(city="Berlin"), semantic_query="robotics",
                student_profile=StudentProfile(nationality="Pakistan"),
            )

    monkeypatch.setattr(parser_module, "get_fallback_llm", lambda schema: FakeChain())

    with caplog.at_level(logging.INFO, logger="daad_search.query_understanding.parser"):
        parse_query("robotics masters in Berlin")

    messages = [record.getMessage() for record in caplog.records]
    assert any("QUERY" in m for m in messages)
    assert any("robotics masters in Berlin" in m for m in messages)
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `pytest tests/test_query_parser.py -k logs_the_raw_query -v`
Expected: FAIL — no `QUERY`-prefixed log record exists yet.

- [ ] **Step 9: Add logging to `parse_query`**

In `src/daad_search/query_understanding/parser.py`, change:

```python
def parse_query(query: str) -> ParsedQuery | None:
    prompt = build_query_prompt(query)
    try:
        return get_fallback_llm(ParsedQuery).invoke(prompt)
    except Exception:
        logger.exception("Failed to parse query across all LLM providers: %r", query)
        return None
```

to:

```python
def parse_query(query: str) -> ParsedQuery | None:
    prompt = build_query_prompt(query)
    capture = ModelNameCapture()
    try:
        parsed = get_fallback_llm(ParsedQuery).invoke(prompt, config={"callbacks": [capture]})
    except Exception:
        logger.exception("Failed to parse query across all LLM providers: %r", query)
        return None
    logger.info(
        "QUERY    raw_query=%r model=%s\n"
        "         filters=%s semantic_query=%r\n"
        "         profile=%s",
        query, capture.model_name,
        parsed.filters.model_dump(), parsed.semantic_query,
        parsed.student_profile.model_dump() if parsed.student_profile else None,
    )
    return parsed
```

and add to the top imports:

```python
from .llm import ModelNameCapture, get_fallback_llm
```

(replacing the existing `from .llm import get_fallback_llm` line).

- [ ] **Step 10: Run the parser tests to verify they pass**

Run: `pytest tests/test_query_parser.py -v`
Expected: all PASS, including `test_parse_query_returns_none_when_all_providers_fail` (still raises `RuntimeError` as intended now that `AlwaysFailsChain.invoke` accepts `config`).

- [ ] **Step 11: Write the failing caplog test for `reason_about_eligibility`**

In `tests/test_eligibility_reasoner.py`, add to the top imports:

```python
import logging

from daad_search.query_understanding.schema import BatchEligibilityReasoning, EligibilityVerdict
```

and add this test:

```python
def test_reason_about_eligibility_logs_one_eligibility_record_per_verdict(monkeypatch, caplog):
    from daad_search.query_understanding import reasoner as reasoner_module

    class FakeChain:
        def invoke(self, prompt, config=None):
            return BatchEligibilityReasoning(verdicts=[
                EligibilityVerdict(program_id=10396, verdict="eligible", reasoning="Meets requirements."),
            ])

    monkeypatch.setattr(reasoner_module, "get_fallback_llm", lambda schema: FakeChain())

    candidates = [
        CandidateForReasoning(
            program_id=10396, course_name="Additive Manufacturing",
            structured_eligibility={"grade_requirement": {"value": 2.5}},
        ),
    ]

    with caplog.at_level(logging.INFO, logger="daad_search.query_understanding.reasoner"):
        reason_about_eligibility(StudentProfile(nationality="Pakistan"), candidates)

    eligibility_logs = [r.getMessage() for r in caplog.records if "ELIGIBILITY" in r.getMessage()]
    assert len(eligibility_logs) == 1
    assert "10396" in eligibility_logs[0]
```

- [ ] **Step 12: Run the test to verify it fails**

Run: `pytest tests/test_eligibility_reasoner.py -k logs_one_eligibility_record -v`
Expected: FAIL — no `ELIGIBILITY`-prefixed log record exists yet.

- [ ] **Step 13: Add logging to `reason_about_eligibility`**

In `src/daad_search/query_understanding/reasoner.py`, change:

```python
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

to:

```python
def reason_about_eligibility(
    profile: StudentProfile, candidates: list[CandidateForReasoning]
) -> list[EligibilityVerdict] | None:
    if not candidates:
        return []
    prompt = build_reasoning_prompt(profile, candidates)
    capture = ModelNameCapture()
    try:
        result: BatchEligibilityReasoning = get_fallback_llm(BatchEligibilityReasoning).invoke(
            prompt, config={"callbacks": [capture]}
        )
    except Exception:
        logger.exception("Failed to reason about eligibility for %d candidates", len(candidates))
        return None

    candidates_by_id = {c.program_id: c for c in candidates}
    for v in result.verdicts:
        candidate = candidates_by_id.get(v.program_id)
        logger.info(
            "ELIGIBILITY  program_id=%s model=%s verdict=%s\n"
            "             profile_input=%s\n"
            "             program_input=%s",
            v.program_id, capture.model_name, v.verdict,
            profile.model_dump(),
            candidate.structured_eligibility if candidate else None,
        )
    return result.verdicts
```

and add to the top imports:

```python
from .llm import ModelNameCapture, get_fallback_llm
```

(replacing the existing `from .llm import get_fallback_llm` line).

- [ ] **Step 14: Run the reasoner tests to verify they pass**

Run: `pytest tests/test_eligibility_reasoner.py -v`
Expected: all PASS, including `test_reason_about_eligibility_returns_none_when_all_providers_fail` (still raises `RuntimeError` as intended).

- [ ] **Step 15: Write the failing test for the RESULTS log line**

Append to `tests/test_query_api.py`:

```python
@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_logs_the_results_outcome(api_client, monkeypatch, caplog):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(filters=SearchFilters(), semantic_query=None, student_profile=StudentProfile()),
    )

    with caplog.at_level(logging.INFO, logger="daad_search.api.query"):
        response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert any("RESULTS" in m and "total_matched=1" in m for m in messages)
```

and add `import logging` to the top of `tests/test_query_api.py` if it isn't already there.

- [ ] **Step 16: Run the test to verify it fails**

Run: `pytest tests/test_query_api.py -k logs_the_results_outcome -v`
Expected: FAIL — no `RESULTS`-prefixed log record exists yet.

- [ ] **Step 17: Add logging to `handle_query`**

In `src/daad_search/api/query.py`, add to the top imports:

```python
import logging
```

and add, right after the imports:

```python
logger = logging.getLogger(__name__)
```

Then, right after the line `results, total = await search_module.hybrid_search(...)` / `results, total = await search_module.filtered_search(...)` `if/else` block (i.e. right after `total` is set, before `reasoning_pool = results[:REASONING_CANDIDATE_CAP]`), add:

```python

    logger.info("RESULTS  total_matched=%d returned_ids=%s", total, [r.id for r in results])
```

- [ ] **Step 18: Run the test to verify it passes**

Run: `pytest tests/test_query_api.py -v`
Expected: all PASS.

- [ ] **Step 19: Fix the root logging-config gap**

In `src/daad_search/api/main.py`, add near the very top of the file, before the other imports:

```python
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
```

- [ ] **Step 20: Run the full backend test suite**

Run: `pytest -m "not integration" -v`
Expected: all PASS.

- [ ] **Step 21: Commit**

```bash
git add src/daad_search/api/main.py src/daad_search/query_understanding/llm.py \
  src/daad_search/query_understanding/parser.py src/daad_search/query_understanding/reasoner.py \
  src/daad_search/api/query.py tests/test_query_understanding_llm.py tests/test_query_parser.py \
  tests/test_eligibility_reasoner.py tests/test_query_api.py tests/test_llm_observability.py
git commit -m "feat: structured production logging for query parsing, search results, and eligibility reasoning"
```

---

## Task 8: Frontend — turbo-snail loading indicator

**Files:**
- Create: `frontend/src/components/TurboSnailLoader.tsx`
- Create: `frontend/src/components/TurboSnailLoader.test.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/ResultsList.tsx`
- Modify: `frontend/src/components/ResultsList.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing tests for TurboSnailLoader**

Create `frontend/src/components/TurboSnailLoader.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TurboSnailLoader } from "./TurboSnailLoader";

describe("TurboSnailLoader", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the first stage's text immediately on mount", () => {
    render(<TurboSnailLoader />);
    expect(screen.getByText("Waking up the server...")).toBeInTheDocument();
  });

  it("advances to the second stage's text after 2 seconds", () => {
    render(<TurboSnailLoader />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("Reading your query...")).toBeInTheDocument();
  });

  it("advances to the third stage's text after 4 seconds", () => {
    render(<TurboSnailLoader />);
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.getByText("Matching programs...")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- TurboSnailLoader.test.tsx`
Expected: FAIL — `Cannot find module './TurboSnailLoader'`.

- [ ] **Step 3: Create TurboSnailLoader**

Create `frontend/src/components/TurboSnailLoader.tsx`:

```tsx
import { useEffect, useState } from "react";

const STAGES = [
  { text: "Waking up the server...", emoji: "🐌", animationClass: "animate-snail-1" },
  { text: "Reading your query...", emoji: "🐌💨", animationClass: "animate-snail-2" },
  { text: "Matching programs...", emoji: "🐌💨💨", animationClass: "animate-snail-3" },
] as const;

export function TurboSnailLoader() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timers = [
      setTimeout(() => setStage(1), 2000),
      setTimeout(() => setStage(2), 4000),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  const current = STAGES[stage];
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center" data-testid="turbo-snail-loader">
      <span className={`text-4xl ${current.animationClass}`}>{current.emoji}</span>
      <p className="text-sm text-ink/70">{current.text}</p>
    </div>
  );
}
```

- [ ] **Step 4: Add the CSS keyframes**

In `frontend/src/index.css`, add after the existing `body { @apply ... }` block:

```css
@keyframes snail-1 {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(2px); }
}
@keyframes snail-2 {
  0%, 100% { transform: translateX(-2px); }
  50% { transform: translateX(3px); }
}
@keyframes snail-3 {
  0%, 100% { transform: translateX(-4px); }
  50% { transform: translateX(4px); }
}

.animate-snail-1 { animation: snail-1 1.2s ease-in-out infinite; }
.animate-snail-2 { animation: snail-2 0.6s ease-in-out infinite; }
.animate-snail-3 { animation: snail-3 0.3s ease-in-out infinite; }
```

- [ ] **Step 5: Run the TurboSnailLoader tests to verify they pass**

Run: `npm test -- TurboSnailLoader.test.tsx`
Expected: all PASS.

- [ ] **Step 6: Write the failing tests for ResultsList's new prop**

Read `frontend/src/components/ResultsList.test.tsx` first. Replace the whole file with:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QueryResult } from "../types";
import { ResultsList } from "./ResultsList";

const RESULT: QueryResult = {
  id: 1, course_name: "Robotics MSc", university: "TU X", city: "Berlin", languages: ["English"],
  subject: null, tuition_fees_text: "No tuition fees", application_deadline_text: "15 July",
  link: "https://example.com",
  score: null, eligibility_verdict: "eligible", eligibility_reasoning: "Meets the grade threshold.",
};

describe("ResultsList", () => {
  it("shows the turbo-snail loader when isQueryPending is true, regardless of isLoading", () => {
    render(<ResultsList results={[]} isLoading={false} isQueryPending={true} onSelectProgram={vi.fn()} />);
    expect(screen.getByTestId("turbo-snail-loader")).toBeInTheDocument();
  });

  it("shows a loading skeleton while isLoading is true and isQueryPending is false", () => {
    render(<ResultsList results={[]} isLoading={true} isQueryPending={false} onSelectProgram={vi.fn()} />);
    expect(screen.getByTestId("results-loading")).toBeInTheDocument();
  });

  it("shows the empty state when there are no results", () => {
    render(<ResultsList results={[]} isLoading={false} isQueryPending={false} onSelectProgram={vi.fn()} />);
    expect(screen.getByText(/no programs matched/i)).toBeInTheDocument();
  });

  it("renders a card per result with its verdict badge, and calls onSelectProgram when clicked", async () => {
    const onSelectProgram = vi.fn();
    render(<ResultsList results={[RESULT]} isLoading={false} isQueryPending={false} onSelectProgram={onSelectProgram} />);

    expect(screen.getByText("Robotics MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByText("English · No tuition fees · 15 July")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Robotics MSc"));
    expect(onSelectProgram).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 7: Run the tests to verify the new ones fail**

Run: `npm test -- ResultsList.test.tsx`
Expected: FAIL on the `isQueryPending` tests (prop doesn't exist yet, TypeScript will also flag the missing prop on every call).

- [ ] **Step 8: Add `isQueryPending` to ResultsList**

Replace `frontend/src/components/ResultsList.tsx` with:

```tsx
import type { QueryResult } from "../types";
import { ResultCard } from "./ResultCard";
import { TurboSnailLoader } from "./TurboSnailLoader";

interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  isQueryPending: boolean;
  onSelectProgram: (id: number) => void;
}

export function ResultsList({ results, isLoading, isQueryPending, onSelectProgram }: ResultsListProps) {
  if (isQueryPending) {
    return <TurboSnailLoader />;
  }

  if (isLoading) {
    return (
      <div className="space-y-3" data-testid="results-loading">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-2xl bg-line/50" />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-ink/70">No programs matched — try loosening a filter or rephrasing.</p>
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

- [ ] **Step 9: Run the ResultsList tests to verify they pass**

Run: `npm test -- ResultsList.test.tsx`
Expected: all PASS.

- [ ] **Step 10: Wire the split loading props into App.tsx**

Read `frontend/src/App.tsx` first (as left by Task 2 — it currently has `results={resultsForDisplay}` and `isLoading={querySearch.isPending || filteredSearch.isPending}` on the `<ResultsList>` element). Change:

```tsx
          <ResultsList
            results={resultsForDisplay}
            isLoading={querySearch.isPending || filteredSearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />
```

to:

```tsx
          <ResultsList
            results={resultsForDisplay}
            isLoading={filteredSearch.isPending}
            isQueryPending={querySearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />
```

- [ ] **Step 11: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS — `App.test.tsx`'s tests still find their final results (MSW resolves fast enough that the transient `TurboSnailLoader` render, which isn't asserted on, doesn't block `findByText` waits).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/components/TurboSnailLoader.tsx frontend/src/components/TurboSnailLoader.test.tsx \
  frontend/src/index.css frontend/src/components/ResultsList.tsx frontend/src/components/ResultsList.test.tsx \
  frontend/src/App.tsx
git commit -m "feat: staged turbo-snail loading indicator for the initial query"
```

---

## Final check

After all 8 tasks: run `pytest -m "not integration"` from the repo root and `npm test` from `frontend/`, both fully green. Then run `pytest -m integration` if Docker Compose services (Postgres/Qdrant) and API keys are available, to catch anything only the real LLM fallback chain or real DB would surface.
