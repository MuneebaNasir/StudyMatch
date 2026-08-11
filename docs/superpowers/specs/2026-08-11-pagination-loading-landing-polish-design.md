# Pagination Cost Fix, Loading Polish & Landing Redesign — Design

## Context

The app (spec history: `2026-08-06-frontend-design.md`, `2026-08-07-frontend-redesign-design.md`, `2026-08-10-eligibility-and-ux-polish-design.md`) is live and was just extended with on-demand eligibility, collapsible admission-detail sections, query templates, and a staged "turbo-snail" loading indicator. Trying it locally surfaced four issues:

1. **Pagination silently re-runs LLM work and drops verdicts.** `handlePageChange` (`frontend/src/App.tsx`) re-issues the *entire* `/query` request on every page change for a query-type search — re-running `parse_query` and the automatic top-1 eligibility reasoning from scratch — and `runQuerySearch`'s `onSuccess` does `setVerdictMap(buildVerdictMap(response.results))`, a wholesale **replace**, not a merge. Paging away from a page discards any verdict fetched for it (including one a user paid an on-demand "Evaluate eligibility" click for), and paging back re-fetches and re-reasons from scratch. This is a real cost/UX regression on a project whose last round was specifically about cutting eligibility-reasoning cost — it was flagged as a deferred minor in that round's final review and is worth fixing now that it's been felt directly.
2. **The loading indicator's copy and motion don't fit every context it's used in.** `TurboSnailLoader` (`frontend/src/components/TurboSnailLoader.tsx`) always shows the same 3-stage "waking up the server / reading your query / matching programs" narrative — but pagination (server already warm, and after fix #1, often an instant cache hit) and the program-detail drawer (a single GET, `frontend/src/components/AdmissionGuideDrawer.tsx`'s plain `"Loading..."` text) don't have a cold-start-and-reasoning pipeline to narrate. Separately, the snail's current motion is a small in-place jitter (`±2-4px` `translateX` oscillation) rather than a visible crawl.
3. **The example-query chips have no framing**, and the pre-filled template gives no signal that it's meant to be edited, not submitted as-is.
4. **The pre-search landing state is visually flat** — `frontend/src/components/Header.tsx` is a bare `<h1>`/`<p>`, next to `ChatQueryBox`'s plain bordered box — compared to the visually rich post-search view (chips, cards, accordion). It should feel like a small, welcoming, "cute" landing moment, not a placeholder.

This spec covers all four, decided through direct conversation with the user.

## Goal

Stop pagination from wasting LLM calls and from losing verdicts a user already paid for; give the loading indicator copy and motion that fit pagination and the program-detail drawer, not just the initial search; frame the example chips and template as editable starting points, not final queries; and turn the pre-search landing view into a warm, on-brand moment using the existing color palette and the snail's own visual identity — without needing any custom art assets.

## Scope

**In scope:** all four items below, frontend-only, no backend changes.

**Explicitly out of scope:**
- Custom illustrations or sourced stock images — infeasible (no image-generation tool available, and sourcing web images risks licensing issues). Emoji-based decoration substitutes for both the "stickers" and "some image" requests, per explicit user decision.
- A "stat chips" row (e.g. "2,400+ programs") on the landing view — considered and explicitly rejected by the user as adding little.
- Caching `filteredSearch` (chip-edit) pages — that path never calls an LLM, so there's no cost concern motivating a cache there; scope stays on the query-search path where the actual waste happens.
- Any change to the "Evaluate eligibility" button's own loading state (`"Evaluating..."` text in `AdmissionGuideDrawer.tsx`) — not raised by the user, left as-is.

---

## Feature 1: Pagination — stop re-fetching and re-losing verdicts

Two changes to `frontend/src/App.tsx`, both required together:

**1a. Cache `/query` responses per page offset**, so revisiting an already-fetched page reuses it instead of re-calling the API (which would re-run `parse_query` and the top-1 reasoning call):

```tsx
const [pageCache, setPageCache] = useState<Map<number, QueryResponse>>(new Map());
```

`runQuerySearch` checks the cache before calling the mutation:

```tsx
function runQuerySearch(query: string, offset: number) {
  setActiveQuery({ type: "query", query });
  const cached = pageCache.get(offset);
  if (cached) {
    setQueryResponse(cached);
    setDisplayedResults(cached.results);
    setActiveFilters(cached.extracted_filters);
    setTotalMatched(cached.total_matched);
    // Deliberately does NOT touch verdictMap here — see 1b for why.
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

The cache is cleared whenever the active query changes: in `handleSubmit` (a genuinely new search) and `handleStartOver`, add `setPageCache(new Map())`.

**1b. `verdictMap` becomes merge-only, never replaced wholesale — and a cache hit must not touch it at all.** This is the subtle half of the fix, worth spelling out:

- On a **fresh fetch** (cache miss), the new page's verdicts are *merged* into the existing `verdictMap` (shown above) instead of replacing it (the current `setVerdictMap(buildVerdictMap(response.results))`). This alone fixes verdicts being lost when moving to a page that's never been fetched before.
- On a **cache hit**, `verdictMap` must be left untouched entirely — not even re-merged with the cached response's own baked-in verdict fields. Reasoning: `pageCache` stores a frozen snapshot of a `QueryResponse` from whenever that page was first fetched. If the user evaluated a program's eligibility on-demand *after* that snapshot was taken, `verdictMap` now holds a more current value than the snapshot does for that program's id. Re-merging the stale snapshot back in (even via the merge in 1a) would overwrite that newer verdict with the old `"no_data"` from the snapshot. Since `resultsForDisplay = mergeVerdicts(displayedResults, verdictMap)` (`App.tsx`, unchanged) always sources the *rendered* verdict from the live `verdictMap` — never from whatever's baked into `displayedResults`/the cached response — leaving `verdictMap` alone on a cache hit is sufficient and correct: the page's cards and the drawer will already show the right, current verdict.

No changes needed to `mergeVerdicts` (`frontend/src/lib/mergeVerdicts.ts`) or `handleEligibilityEvaluated` — both already do the right thing given the above.

## Feature 2: Loading-indicator fixes

**2a. `TurboSnailLoader` gains an optional `message` prop** that switches it from the 3-stage narrative to a single static line with a calm, constant crawl — no stage timers:

```tsx
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

Call sites:
- Initial query (unchanged): `<TurboSnailLoader />`.
- Pagination: `<TurboSnailLoader message="Loading next page..." />`.
- Program-detail drawer (`AdmissionGuideDrawer.tsx`): replaces `{isLoading && <p className="text-sm text-ink/70">Loading...</p>}` with `{isLoading && <TurboSnailLoader message="Fetching program details..." />}`.

**Distinguishing "initial query" from "pagination" in `App.tsx`/`ResultsList.tsx`:** `App.tsx` already tracks `offset`, which is `0` exactly when a fresh search was just submitted (`handleSubmit` always resets it) and `> 0` exactly when paginating forward/back through an already-active query. A cache hit (Feature 1a) never sets `querySearch.isPending` at all (no `.mutate()` call), so it needs no loading state — the page just swaps instantly. `ResultsList`'s single `isQueryPending: boolean` prop becomes two:

```tsx
interface ResultsListProps {
  results: QueryResult[];
  isLoading: boolean;
  isInitialQueryPending: boolean;
  isPaginationPending: boolean;
  onSelectProgram: (id: number) => void;
}
```

with `isInitialQueryPending` checked before `isPaginationPending`, before the existing `isLoading` skeleton. `App.tsx`'s call site:

```tsx
<ResultsList
  results={resultsForDisplay}
  isLoading={filteredSearch.isPending}
  isInitialQueryPending={querySearch.isPending && offset === 0}
  isPaginationPending={querySearch.isPending && offset > 0}
  onSelectProgram={setSelectedProgramId}
/>
```

**2b. Snail motion changes from an in-place jitter to a visible crawl** — sliding back and forth along a short track instead of oscillating a few pixels in place. In `frontend/src/index.css`, the three keyframes (same class names, `animate-snail-1/2/3`, already referenced by `TurboSnailLoader`) get a larger `translateX` range and, for the single-message mode, a calmer default speed (reuses `animate-snail-1`, the slowest/shortest of the three):

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

Amplitude and speed both increase per stage, same escalation principle as before, just with real visible travel instead of a shiver.

## Feature 3: Example-chip framing

In `frontend/src/components/ChatQueryBox.tsx`:

- A caption above the textarea, outside the submitted value entirely (never part of `query`'s state, so there's no risk of it leaking into the actual request):

  ```tsx
  <p className="text-xs text-ink/50">Example query — edit the details below to match your own background.</p>
  ```

- A small label above the two example chips:

  ```tsx
  <p className="text-xs font-medium text-ink/50">Want to see more examples?</p>
  <div className="flex flex-wrap gap-2">
    {/* existing PhD example / Bachelor's example buttons, unchanged */}
  </div>
  ```

No new templates — per explicit user decision, this is framing for the existing two chips, not additional degree-level examples (the catalog is overwhelmingly Bachelor's/Master's/PhD already, and Master's is the pre-filled default).

## Feature 4: Landing-page redesign

Applies **only while `!hasSubmitted`** (`App.tsx`'s existing derived boolean) — once a search has run, the compact header returns and the decorative panel/stickers go away, since the problem being solved is specifically "the *pre-search* view is bland," not the post-search one, and keeping the full decorative treatment on screen after a search would waste vertical space above real results.

**Typography:** `frontend/index.html`'s Google Fonts link gains Comfortaa alongside the existing Inter:

```html
<link
  href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@500;700&family=Inter:wght@400;500;600&display=swap"
  rel="stylesheet"
/>
```

`frontend/tailwind.config.ts` gains a `heading` font-family token, leaving `sans` (Inter, used everywhere else) untouched:

```ts
fontFamily: {
  sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
  heading: ["Comfortaa", "ui-sans-serif", "system-ui", "sans-serif"],
},
```

**Copy** (`Header.tsx`):
- Heading: "Study in Germany" (unchanged text, new font: `font-heading`).
- Subtitle, two lines, replacing the current single line:
  > Your international student counselor for German universities.
  >
  > Write your query below and I'll find the right program for you.

**Decorative panel** (new markup in `App.tsx`, wrapping `Header` and `ChatQueryBox` together, rendered only when `!hasSubmitted`): a soft accent-tinted rounded panel (`bg-accent-soft`, the same token already used for filter chips — no new color needed) containing a fixed arrangement of low-opacity, decorative emoji plus a larger snail mascot emoji near the heading. All decorative emoji are `aria-hidden="true"` and `pointer-events-none` (purely visual, never focusable, never intercept clicks):

```tsx
{!hasSubmitted && (
  <div className="relative overflow-hidden rounded-3xl bg-accent-soft p-6 sm:p-8">
    <span className="pointer-events-none absolute left-4 top-4 text-2xl opacity-30" aria-hidden="true">🎓</span>
    <span className="pointer-events-none absolute right-6 top-6 text-xl opacity-25" aria-hidden="true">🏰</span>
    <span className="pointer-events-none absolute bottom-4 left-10 text-xl opacity-25" aria-hidden="true">🥨</span>
    <span className="pointer-events-none absolute bottom-6 right-10 text-2xl opacity-30" aria-hidden="true">✈️</span>
    <span className="pointer-events-none absolute right-1/3 top-1/2 text-lg opacity-20" aria-hidden="true">📚</span>
    <Header />
    <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />
  </div>
)}
{hasSubmitted && (
  <>
    <Header />
    <ChatQueryBox onSubmit={handleSubmit} isPending={querySearch.isPending} />
  </>
)}
```

`Header.tsx` itself gains the mascot emoji above the heading (shown in both states — it's small and cheap, doesn't need to be conditional):

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

`ChatQueryBox`'s own styling (`rounded-2xl border border-line bg-background p-4 shadow-sm`) is untouched — it keeps its current card look, which now sits visually as a light card on top of the panel's warm background.

**Typing indicator** (`ChatQueryBox.tsx`): a small "🐌 typing..." line that fades in while the user has typed within the last 1.5s and fades out after:

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

```tsx
<p
  className={`text-xs text-ink/40 transition-opacity duration-300 ${isTyping ? "opacity-100" : "opacity-0"}`}
  aria-hidden="true"
>
  🐌 typing...
</p>
```

Kept permanently mounted (not conditionally rendered) so the opacity transition actually animates instead of popping; `aria-hidden` since it's a decorative affordance, not information a screen reader needs (the textarea's own content is already announced as it changes).

## Testing

Following this project's established pattern (Vitest/RTL with MSW-stubbed endpoints, TDD throughout):

- **Feature 1:** a test that paginating to a second page and back to the first does NOT re-issue a `/query` request for the first page's offset (assert the MSW handler's call count, or that a spy on the mutation function isn't called again); a test that an on-demand-evaluated verdict on page 1 survives navigating to page 2 and back.
- **Feature 2:** tests that `TurboSnailLoader` renders the single `message` text with no stage progression when `message` is provided (advancing fake timers should NOT change the text); a test that `ResultsList` shows the initial-query loader only when `isInitialQueryPending` is true, the pagination loader only when `isPaginationPending` is true, and that `AdmissionGuideDrawer` renders `TurboSnailLoader` (not plain text) while `isLoading`.
- **Feature 3:** tests that the caption and "Want to see more examples?" label render, and that the caption's text is never included in what `onSubmit` receives.
- **Feature 4:** a test that `Header`/the decorative panel render only when appropriate (i.e., a test at the `App.tsx` level that the panel/stickers are present before a search and absent after one); a test that typing in the textarea shows the typing indicator and it disappears after the timeout (using fake timers, matching `TurboSnailLoader.test.tsx`'s existing pattern).
