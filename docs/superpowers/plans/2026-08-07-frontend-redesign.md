# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the existing frontend a real identity — name "Study in Germany", a warm/approachable color palette, a proper header — and a matching visual polish pass across existing components, with zero structural or behavioral change.

**Architecture:** Pure styling/copy change. Add named color tokens and a font override to `tailwind.config.ts`, apply them via `index.css`/`index.html`, add one new `Header` component, and swap Tailwind utility classes (color/border/radius only) across five existing components. No component's props, structure, or logic changes.

**Tech Stack:** React + TypeScript + Tailwind CSS (existing). One new asset: Google Fonts (Inter), loaded via `<link>` in `index.html` — no new npm dependency.

## Global Constraints

- App name: "Study in Germany" (page `<title>` and header)
- Tagline: "Your international student counselor for study programmes in Germany" (verbatim — do not paraphrase)
- `ChatQueryBox` placeholder text does NOT change — stays "Describe your background and what you're looking for..."
- No layout/structural change to any component: same props, same DOM structure, same behavior. Only Tailwind utility classes (color, border, radius, font) change.
- Verdict badge colors (`eligible`=green, `not_eligible`=red, `unclear`=amber) keep their meaning — only `likely_eligible` and `no_data` shift hue (see Task 3).
- Color tokens (exact hex values, from the approved spec `docs/superpowers/specs/2026-08-07-frontend-redesign-design.md`):
  - background: `#FBF9F6`
  - ink (text): `#2B2622`
  - accent: `#C1622B`
  - accent soft: `#F3E2D6`
  - warm border/line: `#E7E0D8`

---

## Task 1: Tailwind color tokens, Inter font, page title, base body styles

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: Tailwind utility classes used by every later task — `bg-background`, `text-ink` (+ opacity variants like `text-ink/60`), `bg-accent`, `text-accent`, `ring-accent`, `bg-accent-soft`, `border-line`. Every later task assumes these exist and are correctly wired to the hex values above.

- [ ] **Step 1: Add color tokens and font override to the Tailwind config**

Replace the full contents of `frontend/tailwind.config.ts`:

```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#FBF9F6",
        ink: "#2B2622",
        accent: {
          DEFAULT: "#C1622B",
          soft: "#F3E2D6",
        },
        line: "#E7E0D8",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
```

Note: the spec's color table calls the accent-soft token "`accent-soft`" and the border token "`border-warm`" as plain names. Using a nested `accent: { DEFAULT, soft }` object here is the idiomatic Tailwind way to express "accent" and "a soft variant of accent" as one family (produces clean classes `bg-accent` / `bg-accent-soft`), and the border token is named `line` instead of `border-warm` to avoid the awkward double-prefix class name `border-border-warm` that literal naming would produce. Same hex values, same intended usage — naming only.

- [ ] **Step 2: Add Google Fonts (Inter) and update the page title**

Replace the full contents of `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap"
      rel="stylesheet"
    />
    <title>Study in Germany</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Apply the background/text tokens globally**

Replace the full contents of `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  @apply bg-background text-ink;
}
```

(The font override from Step 1 applies automatically to `html` via Tailwind's base/preflight styles — no extra class needed for that part.)

- [ ] **Step 4: Verify the build still succeeds**

Run: `cd frontend && npm run build`
Expected: succeeds with no errors (this both typechecks and confirms Tailwind can resolve the new config/`@apply` rules with no typos).

- [ ] **Step 5: Run the full frontend test suite to confirm no regressions**

Run: `cd frontend && npm test`
Expected: all existing tests still pass (this task touches no component logic or text content).

- [ ] **Step 6: Commit**

```bash
cd frontend
git add tailwind.config.ts index.html src/index.css
git commit -m "feat: add warm color palette and Inter font"
```

---

## Task 2: Header component (name + tagline)

**Files:**
- Create: `frontend/src/components/Header.tsx`
- Create: `frontend/src/components/Header.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `bg-background`/`text-ink` tokens from Task 1 (indirectly, via inherited body styles) plus `text-ink` directly for its own text color.
- Produces: `Header` — a prop-less component (`export function Header()`) rendering the app name as a heading and the tagline as a paragraph beneath it. Later tasks don't depend on anything from this one beyond it existing and being wired into `App.tsx`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Header.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "./Header";

describe("Header", () => {
  it("renders the site name and tagline", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { name: "Study in Germany" })).toBeInTheDocument();
    expect(
      screen.getByText("Your international student counselor for study programmes in Germany"),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Header.test.tsx`
Expected: FAIL — `Header.tsx` doesn't exist yet (module resolution error).

- [ ] **Step 3: Create the Header component**

Create `frontend/src/components/Header.tsx`:

```tsx
export function Header() {
  return (
    <header>
      <h1 className="text-2xl font-semibold text-ink">Study in Germany</h1>
      <p className="mt-1 text-sm text-ink/60">
        Your international student counselor for study programmes in Germany
      </p>
    </header>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Header.test.tsx`
Expected: PASS

- [ ] **Step 5: Wire Header into App.tsx**

In `frontend/src/App.tsx`, add the import alongside the other component imports:

```tsx
import { Header } from "./components/Header";
```

(insert this line in the existing alphabetized import block, between `import { ChatQueryBox } ...` and `import { ExtractionSummary } ...`)

Then replace this line:

```tsx
      <h1 className="text-2xl font-semibold text-slate-900">DAAD Program Search</h1>
```

with:

```tsx
      <Header />
```

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests pass, including the new `Header.test.tsx` and the existing `App.test.tsx` suite (no existing test asserts the old "DAAD Program Search" text, so nothing else should need updating here).

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/components/Header.tsx src/components/Header.test.tsx src/App.tsx
git commit -m "feat: add Header component with app name and tagline"
```

---

## Task 3: Verdict badge color updates

**Files:**
- Modify: `frontend/src/lib/verdictDisplay.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: no interface change — `VERDICT_STYLES`/`VERDICT_LABELS` keep their exact shape (`Record<EligibilityVerdictValue, string>`), only the string *values* for `likely_eligible` and `no_data` change. Every consumer (`ResultCard`, `AdmissionGuideDrawer`) is unaffected at the type/usage level.

- [ ] **Step 1: Update the two color values**

In `frontend/src/lib/verdictDisplay.ts`, change:

```ts
  likely_eligible: "bg-lime-100 text-lime-800",
```

to:

```ts
  likely_eligible: "bg-orange-100 text-orange-800",
```

and change:

```ts
  no_data: "bg-slate-100 text-slate-600",
```

to:

```ts
  no_data: "bg-stone-100 text-stone-600",
```

(`eligible` stays green, `not_eligible` stays red, `unclear` stays amber — unchanged. `likely_eligible` moves from a cool lime to a warm orange so it doesn't clash with the new palette and stays visually distinct from `unclear`'s amber. `no_data` moves from cool slate to warm stone for the same reason.)

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests pass unchanged — existing tests assert the rendered *label* text (e.g. `"Eligible"`, `"Not evaluated"`) via `VERDICT_LABELS`, never the CSS class strings, so this change is invisible to them.

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/lib/verdictDisplay.ts
git commit -m "fix: warm up likely_eligible and no_data verdict badge colors"
```

---

## Task 4: ChatQueryBox visual polish

**Files:**
- Modify: `frontend/src/components/ChatQueryBox.tsx`

**Interfaces:** No change — same props, same placeholder text, same behavior. Only `className` strings change.

- [ ] **Step 1: Update the form, textarea, and button classes**

In `frontend/src/components/ChatQueryBox.tsx`, replace the `<form>` className:

```tsx
      className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
```

with:

```tsx
      className="flex flex-col gap-3 rounded-2xl border border-line bg-background p-4 shadow-sm"
```

Replace the `<textarea>` className:

```tsx
        className="resize-none rounded-lg border border-slate-200 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
```

with:

```tsx
        className="resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
```

Replace the `<button>` className:

```tsx
        className="self-end rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
```

with:

```tsx
        className="self-end rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
```

Leave the `placeholder` attribute, `rows`, and all logic exactly as they are — do not touch them.

- [ ] **Step 2: Run the ChatQueryBox test suite**

Run: `cd frontend && npx vitest run src/components/ChatQueryBox.test.tsx`
Expected: all pass unchanged (these tests check the placeholder text is present, that submit fires with trimmed text, and pending-state button text — none of which changed).

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/components/ChatQueryBox.tsx
git commit -m "style: warm up ChatQueryBox colors"
```

---

## Task 5: ExtractionSummary chip visual polish

**Files:**
- Modify: `frontend/src/components/ExtractionSummary.tsx`

**Interfaces:** No change — same props, same chip text/removal logic. Only `className` strings change.

- [ ] **Step 1: Update the filter chip and profile chip classes**

In `frontend/src/components/ExtractionSummary.tsx`, replace the filter chip `<span>` className:

```tsx
          className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
```

with:

```tsx
          className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-3 py-1 text-xs text-ink"
```

Replace the remove button className:

```tsx
            className="ml-1 text-slate-400 hover:text-slate-700"
```

with:

```tsx
            className="ml-1 text-ink/40 hover:text-ink"
```

Replace the profile chip `<span>` className:

```tsx
          className="inline-flex items-center rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-500"
```

with:

```tsx
          className="inline-flex items-center rounded-full bg-line/40 px-3 py-1 text-xs text-ink/60"
```

Replace the "couldn't extract" notice `<p>` className:

```tsx
      <p className="text-sm text-slate-500">
```

with:

```tsx
      <p className="text-sm text-ink/60">
```

- [ ] **Step 2: Run the ExtractionSummary test suite**

Run: `cd frontend && npx vitest run src/components/ExtractionSummary.test.tsx`
Expected: all pass unchanged (tests check chip text content and the remove-button click behavior, not colors).

- [ ] **Step 3: Commit**

```bash
cd frontend
git add src/components/ExtractionSummary.tsx
git commit -m "style: warm up ExtractionSummary chip colors"
```

---

## Task 6: ResultCard and ResultsList visual polish

**Files:**
- Modify: `frontend/src/components/ResultCard.tsx`
- Modify: `frontend/src/components/ResultsList.tsx`

**Interfaces:** No change — same props on both components. Only `className` strings change.

- [ ] **Step 1: Update ResultCard classes**

In `frontend/src/components/ResultCard.tsx`, replace the `<button>` className:

```tsx
      className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-slate-400"
```

with:

```tsx
      className="w-full rounded-2xl border border-line bg-background p-4 text-left shadow-sm hover:border-accent"
```

Replace the course name `<h3>` className:

```tsx
          <h3 className="font-medium text-slate-900">{result.course_name}</h3>
```

with:

```tsx
          <h3 className="font-medium text-ink">{result.course_name}</h3>
```

Replace the university/city `<p>` className:

```tsx
          <p className="text-sm text-slate-500">
```

with:

```tsx
          <p className="text-sm text-ink/60">
```

Replace the meta line `<p>` className:

```tsx
      {metaLine && <p className="mt-1 text-xs text-slate-400">{metaLine}</p>}
```

with:

```tsx
      {metaLine && <p className="mt-1 text-xs text-ink/40">{metaLine}</p>}
```

Replace the reasoning `<p>` className:

```tsx
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{result.eligibility_reasoning}</p>
```

with:

```tsx
        <p className="mt-2 line-clamp-2 text-sm text-ink/70">{result.eligibility_reasoning}</p>
```

- [ ] **Step 2: Update ResultsList classes**

In `frontend/src/components/ResultsList.tsx`, replace the loading skeleton className:

```tsx
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
```

with:

```tsx
          <div key={i} className="h-20 animate-pulse rounded-2xl bg-line/50" />
```

Replace the empty-state `<p>` className:

```tsx
      <p className="text-sm text-slate-500">No programs matched — try loosening a filter or rephrasing.</p>
```

with:

```tsx
      <p className="text-sm text-ink/60">No programs matched — try loosening a filter or rephrasing.</p>
```

- [ ] **Step 3: Run the ResultsList test suite**

There is no separate `ResultCard.test.tsx` — `ResultCard` is covered indirectly through `ResultsList.test.tsx`, which renders it.

Run: `cd frontend && npx vitest run src/components/ResultsList.test.tsx`
Expected: all pass unchanged (these tests check rendered text and verdict labels, not colors).

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/components/ResultCard.tsx src/components/ResultsList.tsx
git commit -m "style: warm up ResultCard and ResultsList colors"
```

---

## Task 7: AdmissionGuideDrawer visual polish, and final full-suite verification

**Files:**
- Modify: `frontend/src/components/AdmissionGuideDrawer.tsx`

**Interfaces:** No change — same props, same structure (structured summary + original details both still render, per the already-merged behavior). Only `className` strings change.

- [ ] **Step 1: Update the drawer container and close button classes**

In `frontend/src/components/AdmissionGuideDrawer.tsx`, replace the `Dialog.Content` className:

```tsx
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl">
```

with:

```tsx
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-background p-6 shadow-xl">
```

Replace the `Dialog.Close` className:

```tsx
            <Dialog.Close aria-label="Close" className="text-slate-400 hover:text-slate-700">
```

with:

```tsx
            <Dialog.Close aria-label="Close" className="text-ink/40 hover:text-ink">
```

- [ ] **Step 2: Update the loading/error text and the program link**

Replace:

```tsx
          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-slate-500">Loading...</p>}
```

with:

```tsx
          {isError && <p className="text-sm text-red-600">Couldn't load this program's details.</p>}
          {isLoading && <p className="text-sm text-ink/60">Loading...</p>}
```

(the error text stays red — that's a semantic error color, not part of the warm palette)

Replace the "View program page" link className:

```tsx
                className="text-sm font-medium text-blue-600 hover:underline"
```

with:

```tsx
                className="text-sm font-medium text-accent hover:underline"
```

- [ ] **Step 3: Update the Eligibility section and requirement rows**

Replace:

```tsx
                  <h3 className="text-sm font-medium text-slate-900">Eligibility</h3>
```

with:

```tsx
                  <h3 className="text-sm font-medium text-ink">Eligibility</h3>
```

Replace:

```tsx
                  <p className="mt-1 text-sm text-slate-600">{verdict.eligibility_reasoning ?? "No reasoning available."}</p>
```

with:

```tsx
                  <p className="mt-1 text-sm text-ink/70">{verdict.eligibility_reasoning ?? "No reasoning available."}</p>
```

Replace the "Original program details" heading:

```tsx
                <h3 className="text-sm font-medium text-slate-900">Original program details</h3>
```

with:

```tsx
                <h3 className="text-sm font-medium text-ink">Original program details</h3>
```

Replace `RequirementRow`'s container className:

```tsx
    <div className="rounded-lg border border-slate-100 p-3">
      <p className="text-sm font-medium text-slate-900">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-slate-500">"{quote}"</p>}
```

with:

```tsx
    <div className="rounded-lg border border-line p-3">
      <p className="text-sm font-medium text-ink">{label}</p>
      {quote && <p className="mt-1 text-xs italic text-ink/60">"{quote}"</p>}
```

- [ ] **Step 4: Update RawAdmissionText classes**

Replace:

```tsx
    return <p className="text-sm text-slate-500">No admission text available for this program.</p>;
```

with:

```tsx
    return <p className="text-sm text-ink/60">No admission text available for this program.</p>;
```

Replace:

```tsx
          <h4 className="text-xs font-medium uppercase text-slate-400">{key.replace(/_/g, " ")}</h4>
          <p className="text-sm text-slate-700">{text}</p>
```

with:

```tsx
          <h4 className="text-xs font-medium uppercase text-ink/40">{key.replace(/_/g, " ")}</h4>
          <p className="text-sm text-ink/80">{text}</p>
```

- [ ] **Step 5: Run the AdmissionGuideDrawer test suite**

Run: `cd frontend && npx vitest run src/components/AdmissionGuideDrawer.test.tsx`
Expected: all pass unchanged (tests check rendered text, verdict labels, and the link's `href` — not colors).

- [ ] **Step 6: Run the full frontend test suite and production build as a final check**

Run: `cd frontend && npm test`
Expected: all tests pass (this is the last task — this is the final regression check across every component touched in this plan).

Run: `cd frontend && npm run build`
Expected: succeeds with no TypeScript or build errors.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/components/AdmissionGuideDrawer.tsx
git commit -m "style: warm up AdmissionGuideDrawer colors"
```
