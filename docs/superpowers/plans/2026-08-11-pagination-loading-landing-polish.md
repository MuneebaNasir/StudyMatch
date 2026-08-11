# Pagination Cost Fix, Loading Polish & Landing Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four items in `docs/superpowers/specs/2026-08-11-pagination-loading-landing-polish-design.md`: stop pagination from wasting LLM calls and losing on-demand verdicts, give the loading indicator copy/motion that fit pagination and the program-detail drawer, frame the example-query chips and template as editable starting points, and give the app a warm, "cute," on-brand look before and after searching.

**Architecture:** Frontend-only (`frontend/src/`). No backend changes, no new dependencies (Comfortaa is loaded via the existing Google Fonts `<link>` pattern already used for Inter). Every change is additive to existing components; no new files are created.

**Tech Stack:** React + TypeScript + Vite + TanStack Query + Tailwind CSS (frontend), Vitest + Testing Library + MSW (tests).

## Global Constraints

- A **fresh** `/query` response's verdicts are **merged** into `verdictMap` (never replace it wholesale). A **cached** (already-seen) page's response must leave `verdictMap` completely untouched — see Task 1's Step 5 for the exact reasoning; getting this backwards silently reintroduces the bug this plan fixes.
- `pageCache` (new `App.tsx` state) is cleared in `handleSubmit` and `handleStartOver` only. `runFilteredSearch`/`handleFiltersChange` never reads or writes it.
- `TurboSnailLoader`'s new `message` prop, when provided, disables the 3-stage timer entirely (single static message, no progression).
- The example-query caption ("Example query — edit the details below...") and the "Want to see more examples?" label are presentational text only — never part of `ChatQueryBox`'s `query` state or the string passed to `onSubmit`.
- New font token is `font-heading` (Comfortaa); the existing `font-sans` (Inter) default is untouched everywhere else.
- All decorative emoji (background stickers, mascot) carry `aria-hidden="true"` and `pointer-events-none`.
- TDD throughout, following this repo's existing Vitest + Testing Library + MSW conventions exactly. When a test combines `userEvent` with `vi.useFakeTimers()`, create the user with `userEvent.setup({ delay: null })` — combining fake timers with `userEvent`'s default artificial delays causes tests to hang; this is the standard fix, already needed once in this plan (Task 4).

---

## Task 1: Pagination — stop re-fetching and re-losing verdicts

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing test for cache behavior**

Read `frontend/src/App.test.tsx` first (it has 4 existing tests; the "pages through results" test at the bottom is the closest existing pattern to follow). Add this test to the `describe("App", ...)` block:

```tsx
  it("does not re-fetch a page that's already been loaded when paginating back to it", async () => {
    const offsetCalls: number[] = [];
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = (await request.json()) as { offset: number };
        offsetCalls.push(body.offset);
        return HttpResponse.json({
          results: [{
            id: body.offset + 1, course_name: `Course ${body.offset + 1}`, university: "TU X", city: null,
            languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
            link: "https://example.com", score: null, eligibility_verdict: "no_data" as const, eligibility_reasoning: null,
          }],
          total_matched: 45,
          extracted_filters: null, extracted_profile: null, semantic_query: null,
        });
      }),
    );

    renderApp();

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText("Course 1")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(await screen.findByText("Course 21")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /previous/i }));
    expect(await screen.findByText("Course 1")).toBeInTheDocument();

    expect(offsetCalls).toEqual([0, 20]);
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- App.test.tsx` (from `frontend/`)
Expected: FAIL — `offsetCalls` will be `[0, 20, 0]` (three calls, not two), since the current code re-fetches offset 0 on "Previous".

- [ ] **Step 3: Write the failing test for verdict persistence**

Add this test to the same `describe` block:

```tsx
  it("keeps an on-demand-evaluated verdict after paginating away and back", async () => {
    let page0Calls = 0;
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = (await request.json()) as { offset: number };
        if (body.offset === 0) {
          page0Calls += 1;
          return HttpResponse.json({
            results: [{
              id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
              languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
              link: "https://example.com/1", score: 0.9, eligibility_verdict: "no_data", eligibility_reasoning: null,
            }],
            total_matched: 25,
            extracted_filters: { languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null },
            extracted_profile: { degree_field: null, grade_value: null, grade_scale: null, nationality: "Pakistan", other_notes: null },
            semantic_query: "robotics",
          });
        }
        return HttpResponse.json({
          results: [{
            id: 21, course_name: "Data Science MSc", university: "TU X", city: null,
            languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
            link: "https://example.com/21", score: null, eligibility_verdict: "no_data" as const, eligibility_reasoning: null,
          }],
          total_matched: 25,
          extracted_filters: null, extracted_profile: null, semantic_query: null,
        });
      }),
      http.get(`${API_BASE_URL}/programs/1`, () =>
        HttpResponse.json({
          id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
          languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
          link: "https://example.com/1", score: 0.9, course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: {},
          structured_eligibility: {
            requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: null,
            extraction_confidence: "high", degree_prerequisite: null, grade_requirement: null,
            standardized_tests: [], language_requirements: [], notes: null,
          },
        }),
      ),
      http.post(`${API_BASE_URL}/programs/1/evaluate-eligibility`, () =>
        HttpResponse.json({ eligibility_verdict: "eligible", eligibility_reasoning: "Meets all requirements." }),
      ),
    );

    renderApp();

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(page0Calls).toBe(1);

    await userEvent.click(screen.getByText("Robotics Engineering MSc"));
    await userEvent.click(await screen.findByRole("button", { name: /evaluate eligibility/i }));
    await waitFor(() => expect(screen.getByText("Eligible")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /close/i }));

    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(await screen.findByText("Data Science MSc")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /previous/i }));
    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(page0Calls).toBe(1);
  });
```

- [ ] **Step 4: Run both new tests to verify they fail**

Run: `npm test -- App.test.tsx`
Expected: FAIL on both new tests — the second one fails because paging back to page 0 re-fetches it with `eligibility_verdict: "no_data"` again, wiping out the on-demand-evaluated `"eligible"` verdict.

- [ ] **Step 5: Implement the fix in `App.tsx`**

Read `frontend/src/App.tsx` first. Change:

```tsx
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
```

to:

```tsx
  function runQuerySearch(query: string, offset: number) {
    setActiveQuery({ type: "query", query });
    const cached = pageCache.get(offset);
    if (cached) {
      setQueryResponse(cached);
      setDisplayedResults(cached.results);
      setActiveFilters(cached.extracted_filters);
      setTotalMatched(cached.total_matched);
      // Deliberately does NOT touch verdictMap. pageCache holds a frozen
      // snapshot from whenever this page was first fetched; if the user
      // evaluated a program on-demand since then, verdictMap already holds
      // a more current value than the snapshot does for that id. Re-merging
      // the stale snapshot would overwrite it. resultsForDisplay always
      // reads verdicts from the live verdictMap, never from what's baked
      // into displayedResults/the cached response, so leaving it alone here
      // is correct.
      return;
    }
    querySearch.mutate(
      { query, offset },
      {
        onSuccess: (response) => {
          setPageCache((previous) => new Map(previous).set(offset, response));
          setQueryResponse(response);
          setDisplayedResults(response.results);
          setActiveFilters(response.extracted_filters);
          setTotalMatched(response.total_matched);
          setVerdictMap((previous) => {
            const merged = new Map(previous);
            for (const [id, info] of buildVerdictMap(response.results)) {
              merged.set(id, info);
            }
            return merged;
          });
        },
      },
    );
  }
```

Add the `pageCache` state declaration, right after the existing `totalMatched` state:

```tsx
  const [totalMatched, setTotalMatched] = useState(0);
  const [pageCache, setPageCache] = useState<Map<number, QueryResponse>>(new Map());
```

Clear the cache on a genuinely new search — in `handleSubmit`, change:

```tsx
  function handleSubmit(query: string) {
    setOffset(0);
    runQuerySearch(query, 0);
  }
```

to:

```tsx
  function handleSubmit(query: string) {
    setOffset(0);
    setPageCache(new Map());
    runQuerySearch(query, 0);
  }
```

And in `handleStartOver`, add `setPageCache(new Map());` alongside the other resets:

```tsx
  function handleStartOver() {
    setQueryResponse(null);
    setDisplayedResults([]);
    setActiveFilters(null);
    setVerdictMap(new Map());
    setPageCache(new Map());
    setSelectedProgramId(null);
    setActiveQuery(null);
    setOffset(0);
    setTotalMatched(0);
    querySearch.reset();
    filteredSearch.reset();
  }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm test -- App.test.tsx`
Expected: all PASS, including the 4 pre-existing tests in this file (none of them revisit an already-fetched page, so the cache is a no-op for them).

- [ ] **Step 7: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "fix: cache query pages and merge verdicts so pagination stops re-evaluating eligibility"
```

---

## Task 2: Loading-indicator fixes — context-appropriate copy and a real crawl

**Files:**
- Modify: `frontend/src/components/TurboSnailLoader.tsx`
- Modify: `frontend/src/components/TurboSnailLoader.test.tsx`
- Modify: `frontend/src/components/ResultsList.tsx`
- Modify: `frontend/src/components/ResultsList.test.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.tsx`
- Modify: `frontend/src/components/AdmissionGuideDrawer.test.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 1's `App.tsx` (already has `offset` state, untouched by Task 1's changes).
- Produces: `TurboSnailLoader` gains an optional `message?: string` prop — Task 4 does not touch this component, no downstream dependency.

- [ ] **Step 1: Write the failing tests for `TurboSnailLoader`'s new mode**

Read `frontend/src/components/TurboSnailLoader.test.tsx` first. Add these two tests to the existing `describe` block (which already has `beforeEach`/`afterEach` fake-timer setup):

```tsx
  it("renders a fixed message with no stage progression when message is provided", () => {
    render(<TurboSnailLoader message="Loading next page..." />);
    expect(screen.getByText("Loading next page...")).toBeInTheDocument();
  });

  it("does not advance to a different stage over time when message is provided", () => {
    render(<TurboSnailLoader message="Loading next page..." />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText("Loading next page...")).toBeInTheDocument();
    expect(screen.queryByText("Reading your query...")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- TurboSnailLoader.test.tsx`
Expected: FAIL — `message` prop doesn't exist yet (TypeScript will also flag it).

- [ ] **Step 3: Add the `message` prop to `TurboSnailLoader`**

Replace `frontend/src/components/TurboSnailLoader.tsx` with:

```tsx
import { useEffect, useState } from "react";

const STAGES = [
  { text: "Waking up the server...", emoji: "🐌", animationClass: "animate-snail-1" },
  { text: "Reading your query...", emoji: "🐌💨", animationClass: "animate-snail-2" },
  { text: "Matching programs...", emoji: "🐌💨💨", animationClass: "animate-snail-3" },
] as const;

interface TurboSnailLoaderProps {
  message?: string;
}

export function TurboSnailLoader({ message }: TurboSnailLoaderProps) {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (message) return;
    const timers = [
      setTimeout(() => setStage(1), 2000),
      setTimeout(() => setStage(2), 4000),
    ];
    return () => timers.forEach(clearTimeout);
  }, [message]);

  const current = message
    ? { text: message, emoji: "🐌", animationClass: "animate-snail-1" }
    : STAGES[stage];

  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center" data-testid="turbo-snail-loader">
      <span className={`text-4xl ${current.animationClass}`}>{current.emoji}</span>
      <p className="text-sm text-ink/70">{current.text}</p>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- TurboSnailLoader.test.tsx`
Expected: all 5 tests PASS.

- [ ] **Step 5: Write the failing tests for `ResultsList`'s split props**

Replace `frontend/src/components/ResultsList.test.tsx` with:

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
  it("shows the turbo-snail loader (3-stage) when isInitialQueryPending is true, regardless of the other flags", () => {
    render(
      <ResultsList
        results={[]} isLoading={false} isInitialQueryPending={true} isPaginationPending={false}
        onSelectProgram={vi.fn()}
      />,
    );
    expect(screen.getByTestId("turbo-snail-loader")).toBeInTheDocument();
    expect(screen.getByText("Waking up the server...")).toBeInTheDocument();
  });

  it("shows the turbo-snail loader with pagination copy when isPaginationPending is true", () => {
    render(
      <ResultsList
        results={[]} isLoading={false} isInitialQueryPending={false} isPaginationPending={true}
        onSelectProgram={vi.fn()}
      />,
    );
    expect(screen.getByTestId("turbo-snail-loader")).toBeInTheDocument();
    expect(screen.getByText("Loading next page...")).toBeInTheDocument();
  });

  it("shows a loading skeleton while isLoading is true and neither pending flag is set", () => {
    render(
      <ResultsList
        results={[]} isLoading={true} isInitialQueryPending={false} isPaginationPending={false}
        onSelectProgram={vi.fn()}
      />,
    );
    expect(screen.getByTestId("results-loading")).toBeInTheDocument();
  });

  it("shows the empty state when there are no results", () => {
    render(
      <ResultsList
        results={[]} isLoading={false} isInitialQueryPending={false} isPaginationPending={false}
        onSelectProgram={vi.fn()}
      />,
    );
    expect(screen.getByText(/no programs matched/i)).toBeInTheDocument();
  });

  it("renders a card per result with its verdict badge, and calls onSelectProgram when clicked", async () => {
    const onSelectProgram = vi.fn();
    render(
      <ResultsList
        results={[RESULT]} isLoading={false} isInitialQueryPending={false} isPaginationPending={false}
        onSelectProgram={onSelectProgram}
      />,
    );

    expect(screen.getByText("Robotics MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByText("English · No tuition fees · 15 July")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Robotics MSc"));
    expect(onSelectProgram).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `npm test -- ResultsList.test.tsx`
Expected: FAIL — `isInitialQueryPending`/`isPaginationPending` props don't exist yet.

- [ ] **Step 7: Update `ResultsList`**

Replace `frontend/src/components/ResultsList.tsx` with:

```tsx
import type { QueryResult } from "../types";
import { ResultCard } from "./ResultCard";
import { TurboSnailLoader } from "./TurboSnailLoader";

interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  isInitialQueryPending: boolean;
  isPaginationPending: boolean;
  onSelectProgram: (id: number) => void;
}

export function ResultsList({
  results, isLoading, isInitialQueryPending, isPaginationPending, onSelectProgram,
}: ResultsListProps) {
  if (isInitialQueryPending) {
    return <TurboSnailLoader />;
  }

  if (isPaginationPending) {
    return <TurboSnailLoader message="Loading next page..." />;
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

- [ ] **Step 8: Run the `ResultsList` tests to verify they pass**

Run: `npm test -- ResultsList.test.tsx`
Expected: all PASS.

- [ ] **Step 9: Write the failing test for the drawer's loading state**

Read `frontend/src/components/AdmissionGuideDrawer.test.tsx` first. Change the existing test:

```tsx
  it("shows the loading state", () => {
    renderDrawer({ program: undefined, isLoading: true });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
```

to:

```tsx
  it("shows the loading state", () => {
    renderDrawer({ program: undefined, isLoading: true });
    expect(screen.getByText("Fetching program details...")).toBeInTheDocument();
  });
```

- [ ] **Step 10: Run the test to verify it fails**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: FAIL on "shows the loading state" — the current text is plain `"Loading..."`, not `"Fetching program details..."`.

- [ ] **Step 11: Update the drawer's loading state**

In `frontend/src/components/AdmissionGuideDrawer.tsx`, add to the top imports (alongside the existing `useEvaluateEligibility`/`verdictDisplay` imports):

```tsx
import { TurboSnailLoader } from "./TurboSnailLoader";
```

Change:

```tsx
          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-ink/70">Loading...</p>}
```

to:

```tsx
          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <TurboSnailLoader message="Fetching program details..." />}
```

- [ ] **Step 12: Run the drawer tests to verify they pass**

Run: `npm test -- AdmissionGuideDrawer.test.tsx`
Expected: all PASS.

- [ ] **Step 13: Change the snail's motion from an in-place jitter to a crawl**

Replace `frontend/src/index.css`'s keyframes section (everything from `@keyframes snail-1` to the end of the file) with:

```css
@keyframes snail-1 {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(24px); }
}
@keyframes snail-2 {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(32px); }
}
@keyframes snail-3 {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(40px); }
}

.animate-snail-1 { animation: snail-1 1.4s ease-in-out infinite; }
.animate-snail-2 { animation: snail-2 0.9s ease-in-out infinite; }
.animate-snail-3 { animation: snail-3 0.5s ease-in-out infinite; }
```

This is a pure CSS change with no test coverage (matches how the original jitter keyframes were introduced — animation timing/amplitude isn't asserted in tests, only which class is applied, which is already covered by Task 2's earlier steps).

- [ ] **Step 14: Wire the split props into `App.tsx`**

Read `frontend/src/App.tsx` first (as left by Task 1 — it now has `pageCache` state, but the `<ResultsList>` JSX itself is unchanged by Task 1). Change:

```tsx
          <ResultsList
            results={resultsForDisplay}
            isLoading={filteredSearch.isPending}
            isQueryPending={querySearch.isPending}
            onSelectProgram={setSelectedProgramId}
          />
```

to:

```tsx
          <ResultsList
            results={resultsForDisplay}
            isLoading={filteredSearch.isPending}
            isInitialQueryPending={querySearch.isPending && offset === 0}
            isPaginationPending={querySearch.isPending && offset > 0}
            onSelectProgram={setSelectedProgramId}
          />
```

- [ ] **Step 15: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS — `App.test.tsx`'s existing tests still find their final results (the loader swap doesn't change what's rendered once a fetch resolves).

- [ ] **Step 16: Commit**

```bash
git add frontend/src/components/TurboSnailLoader.tsx frontend/src/components/TurboSnailLoader.test.tsx \
  frontend/src/components/ResultsList.tsx frontend/src/components/ResultsList.test.tsx \
  frontend/src/components/AdmissionGuideDrawer.tsx frontend/src/components/AdmissionGuideDrawer.test.tsx \
  frontend/src/index.css frontend/src/App.tsx
git commit -m "feat: context-appropriate loading copy for pagination and program details, snail crawl motion"
```

---

## Task 3: Example-chip framing

**Files:**
- Modify: `frontend/src/components/ChatQueryBox.tsx`
- Modify: `frontend/src/components/ChatQueryBox.test.tsx`

- [ ] **Step 1: Write the failing tests**

Read `frontend/src/components/ChatQueryBox.test.tsx` first. Add these three tests to the existing `describe` block:

```tsx
  it("shows a caption above the textarea explaining it's an editable example", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect(screen.getByText(/example query — edit the details below/i)).toBeInTheDocument();
  });

  it("shows a label inviting the user to see more examples above the chips", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect(screen.getByText("Want to see more examples?")).toBeInTheDocument();
  });

  it("does not include the caption text in the submitted query", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalled();
    const submittedQuery = onSubmit.mock.calls[0][0] as string;
    expect(submittedQuery).not.toContain("Example query");
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: FAIL on the first two (caption and label don't exist yet); the third passes trivially already (harmless — it'll keep passing once the others are implemented correctly, since the caption genuinely never enters `query` state).

- [ ] **Step 3: Add the caption and label**

Read `frontend/src/components/ChatQueryBox.tsx` first. Change:

```tsx
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
```

to:

```tsx
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-2xl border border-line bg-background p-4 shadow-sm"
    >
      <p className="text-xs text-ink/50">Example query — edit the details below to match your own background.</p>
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        rows={5}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <p className="text-xs font-medium text-ink/50">Want to see more examples?</p>
      <div className="flex flex-wrap gap-2">
```

(The closing `</div>` for the chips row and everything after it is unchanged — only the opening tags above it move, and the new caption/label are added.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChatQueryBox.tsx frontend/src/components/ChatQueryBox.test.tsx
git commit -m "feat: frame example query as editable and label the example chips"
```

---

## Task 4: Landing-page redesign — warm typography, decorative panel, typing indicator

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/src/components/Header.tsx`
- Modify: `frontend/src/components/Header.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ChatQueryBox.tsx`
- Modify: `frontend/src/components/ChatQueryBox.test.tsx`

- [ ] **Step 1: Add the Comfortaa font**

In `frontend/index.html`, change:

```html
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
```

to:

```html
    <link
      href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@500;700&family=Inter:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
```

In `frontend/tailwind.config.ts`, change:

```ts
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
```

to:

```ts
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        heading: ["Comfortaa", "ui-sans-serif", "system-ui", "sans-serif"],
      },
```

- [ ] **Step 2: Write the failing test for `Header`'s new copy**

Replace `frontend/src/components/Header.test.tsx` with:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "./Header";

describe("Header", () => {
  it("renders the site name and welcoming tagline", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { name: "Study in Germany" })).toBeInTheDocument();
    expect(
      screen.getByText("Your international student counselor for German universities."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Write your query below and I'll find the right program for you."),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- Header.test.tsx`
Expected: FAIL — the current tagline text is the old single-line copy.

- [ ] **Step 4: Update `Header`**

Replace `frontend/src/components/Header.tsx` with:

```tsx
export function Header() {
  return (
    <header className="text-center">
      <span className="text-4xl" aria-hidden="true">🐌</span>
      <h1 className="mt-2 font-heading text-3xl font-bold text-ink">Study in Germany</h1>
      <p className="mt-2 text-sm text-ink/70">Your international student counselor for German universities.</p>
      <p className="text-sm text-ink/70">Write your query below and I'll find the right program for you.</p>
    </header>
  );
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm test -- Header.test.tsx`
Expected: PASS.

- [ ] **Step 6: Wrap `Header` and `ChatQueryBox` in the decorative panel**

Read `frontend/src/App.tsx` first (as left by Tasks 1 and 2 — it now has `pageCache` state and the split `ResultsList` props; neither affects this step). Change:

```tsx
      <Header />
      <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />
```

to:

```tsx
      <div className="relative overflow-hidden rounded-3xl bg-accent-soft p-6 sm:p-8">
        <span className="pointer-events-none absolute left-4 top-4 text-2xl opacity-30" aria-hidden="true">🎓</span>
        <span className="pointer-events-none absolute right-6 top-6 text-xl opacity-25" aria-hidden="true">🏰</span>
        <span className="pointer-events-none absolute bottom-4 left-10 text-xl opacity-25" aria-hidden="true">🥨</span>
        <span className="pointer-events-none absolute bottom-6 right-10 text-2xl opacity-30" aria-hidden="true">✈️</span>
        <span className="pointer-events-none absolute right-1/3 top-1/2 text-lg opacity-20" aria-hidden="true">📚</span>
        <Header />
        <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />
      </div>
```

No test changes needed for this step — `App.test.tsx`'s existing tests query by role/text (e.g. `screen.getByRole("textbox")`, `screen.getByRole("button", { name: /search programs/i })`), not by DOM ancestry, so wrapping these two components in a new `div` doesn't affect any existing assertion.

- [ ] **Step 7: Run `App.test.tsx` to confirm no regression**

Run: `npm test -- App.test.tsx`
Expected: all PASS (unchanged from Tasks 1-2's state).

- [ ] **Step 8: Write the failing test for the typing indicator**

Read `frontend/src/components/ChatQueryBox.test.tsx` first (as left by Task 3 — it has 8 tests, no fake timers yet). Add to the top imports:

```tsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
```

(replacing the existing `import { render, screen } from "@testing-library/react";` and `import { describe, expect, it, vi } from "vitest";` lines — `act`, `afterEach`, `beforeEach` are new).

Add a new `describe` block after the existing one, at the bottom of the file:

```tsx
describe("ChatQueryBox typing indicator", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the typing indicator while the user is actively typing, then fades it out after a pause", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "a");

    expect(screen.getByText("🐌 typing...")).toHaveClass("opacity-100");

    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(screen.getByText("🐌 typing...")).toHaveClass("opacity-0");
  });
});
```

This is a separate `describe` block specifically so `vi.useFakeTimers()` stays scoped to this one test and doesn't affect the other `describe("ChatQueryBox", ...)` tests in the same file, matching `TurboSnailLoader.test.tsx`'s existing convention. `userEvent.setup({ delay: null })` is required here — combining `userEvent`'s default artificial per-keystroke delay with fake timers causes the test to hang; `delay: null` disables that delay so `userEvent` and `vi.advanceTimersByTime` don't conflict.

- [ ] **Step 9: Run the test to verify it fails**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: FAIL — no element with the text "🐌 typing..." exists yet.

- [ ] **Step 10: Add the typing indicator**

In `frontend/src/components/ChatQueryBox.tsx`, change the top import from:

```tsx
import { type FormEvent, useState } from "react";
```

to:

```tsx
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react";
```

Inside the `ChatQueryBox` function, after the existing `const [query, setQuery] = useState(MASTERS_TEMPLATE);` line, add:

```tsx
  const [isTyping, setIsTyping] = useState(false);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleChange(event: ChangeEvent<HTMLTextAreaElement>) {
    setQuery(event.target.value);
    setIsTyping(true);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => setIsTyping(false), 1500);
  }

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, []);
```

Change the textarea's `onChange` from:

```tsx
        onChange={(event) => setQuery(event.target.value)}
```

to:

```tsx
        onChange={handleChange}
```

Add the indicator between the `<textarea>` and the "Want to see more examples?" paragraph Task 3 added. Change:

```tsx
        onChange={handleChange}
        rows={5}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <p className="text-xs font-medium text-ink/50">Want to see more examples?</p>
```

to:

```tsx
        onChange={handleChange}
        rows={5}
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
      <p
        className={`text-xs text-ink/40 transition-opacity duration-300 ${isTyping ? "opacity-100" : "opacity-0"}`}
        aria-hidden="true"
      >
        🐌 typing...
      </p>
      <p className="text-xs font-medium text-ink/50">Want to see more examples?</p>
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `npm test -- ChatQueryBox.test.tsx`
Expected: all PASS.

- [ ] **Step 12: Run the full frontend test suite**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 13: Commit**

```bash
git add frontend/index.html frontend/tailwind.config.ts frontend/src/components/Header.tsx \
  frontend/src/components/Header.test.tsx frontend/src/App.tsx frontend/src/components/ChatQueryBox.tsx \
  frontend/src/components/ChatQueryBox.test.tsx
git commit -m "feat: warm landing redesign with Comfortaa heading, decorative panel, and typing indicator"
```

---

## Final check

After all 4 tasks: run `npm test` from `frontend/`, fully green, and `npm run build` to confirm TypeScript compiles cleanly across every change.
