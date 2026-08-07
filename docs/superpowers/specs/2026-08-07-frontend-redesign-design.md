# Frontend Redesign — Design

## Context

The frontend (spec: `2026-08-06-frontend-design.md`) is functionally complete and merged to `main`: chat-style query box, editable extraction chips, eligibility-annotated results list, admission-guide side drawer, pagination. It currently uses Tailwind's default theme with no customization — default slate/white palette, no custom fonts, the literal name "DAAD Program Search" as the page title, and a generic placeholder ("Describe your background and what you're looking for...") in the query box.

This spec covers a visual and copy pass only: a name, a color identity, and small copy/UX refinements. No component is restructured, no new features are added, no existing behavior changes.

## Goal

Give the app a real identity — a name, a warm and credible color palette, a header that sets the tone as a "student counselor" rather than a bare search tool — and fix one concrete UX gap (the query box's placeholder doesn't show users what a good query looks like). Everything else about how the app behaves stays exactly as it is today.

## Scope

**In scope:**
- App name: "Study in Germany"
- Tagline under the name: "Your international student counselor for study programmes in Germany"
- A warm, approachable color palette (warm off-white background, warm charcoal text, terracotta accent) applied via Tailwind theme tokens, replacing ad hoc slate/green/red/amber Tailwind defaults where they're used purely for visual styling
- A real header component (name + tagline), replacing the current bare `<h1>`
- `ChatQueryBox` placeholder changed from a generic instruction to a concrete example query
- Visual polish pass on existing components (chips, cards, drawer, buttons): rounder corners, softer shadows, warm-gray borders instead of cool slate — no layout/structural change
- One new dependency: a single web font (Inter, via Google Fonts) applied globally, replacing the browser default sans stack

**Explicitly out of scope:**
- Any change to layout/structure (results list, side drawer, chip behavior, pagination controls all stay exactly where and how they are)
- Any new feature or behavior change
- A logo/icon (text-only header for now)
- Verdict badge *colors* (green/red/amber carry meaning, not brand — see Color System below for the one adjustment made there)
- Deployment (separate, later spec)

## Naming & Copy

- Page `<title>` and header: **"Study in Germany"**
- Tagline, rendered under the name in the header: **"Your international student counselor for study programmes in Germany"**
- `ChatQueryBox` placeholder becomes a concrete example instead of an instruction, e.g.:
  *"I have a Bachelor's in Computer Science, 3.2 GPA, looking for English-taught AI master's programs with no tuition fees..."*
  The textarea keeps an explicit `aria-label="Describe your background and what you're looking for"` so it has a stable, meaningful accessible name independent of the example text shown as placeholder (see Testing — this also decouples tests from copy).

## Color System

Added as Tailwind theme extensions (`tailwind.config.ts`), not one-off utility classes, so the palette is named and reusable:

| Token | Value (approx.) | Used for |
|---|---|---|
| `background` | `#FBF9F6` (warm off-white) | page background |
| `ink` | `#2B2622` (warm charcoal) | headings, primary body text |
| `accent` | `#C1622B` (terracotta) | primary buttons, active/focus states, links |
| `accent-soft` | `#F3E2D6` | subtle accent backgrounds (e.g. hover states) |
| `border-warm` | `#E7E0D8` | card/chip/input borders (replaces `slate-200`) |

Verdict badges (`lib/verdictDisplay.ts`) keep their semantic system (green=eligible, red=not-eligible, amber=unclear — meaning-carrying, not brand colors, changing them would hurt scannability). One concrete adjustment: `likely_eligible` currently uses `lime-100`/`lime-800`, a cool yellow-green that will clash against the new warm off-white/terracotta background — shift it to `amber-100`/`amber-700` (a shade lighter than `unclear`'s `amber-800`, so the two stay visually distinct) or `orange-100`/`orange-800`, whichever reads more clearly distinct from `unclear` during implementation. `no_data` shifts from `slate-100`/`slate-600` to a warm neutral (`stone-100`/`stone-600`) so it doesn't read as a cool gray outlier.

## Typography

Single font family (Inter, loaded via Google Fonts `<link>` in `index.html`) applied globally via Tailwind's `fontFamily.sans` override — no separate display/heading font, keeps this simple. Chosen because it's free, widely used, reads as clean/professional (matches "clean & trustworthy"), and covers the weight range needed (400/500/600) without extra font files.

## Header

New `Header` component: name ("Study in Germany") as a prominent heading, tagline directly under it in a lighter/smaller weight. Replaces the current single `<h1>DAAD Program Search</h1>` in `App.tsx`. No navigation, no logo — just identity.

## Component Polish (no structural change)

Applied via the new color tokens and small Tailwind class changes only — every component keeps its current props, structure, and behavior:
- `ChatQueryBox`: warm border, terracotta focus ring instead of slate, terracotta submit button instead of slate-900
- `ExtractionSummary` chips: warm-gray background/border instead of slate-100
- `ResultCard` / results list: warm-gray borders, softer shadow
- `AdmissionGuideDrawer`: warm background/border, terracotta link color for "View program page"
- Rounded corners increased slightly (`rounded-xl` → `rounded-2xl` where already rounded) for the softer feel described as "warm & approachable"

## Testing

This is a styling/copy pass, so most existing tests are unaffected (they assert behavior and text content, not CSS classes). Two things need updating:
1. All `getByPlaceholderText(/describe your background/i)` call sites (`App.test.tsx` ×4, `ChatQueryBox.test.tsx` ×2) break once the placeholder becomes example text instead of an instruction. Switch these to `getByRole("textbox", { name: /describe your background/i })`, targeting the new `aria-label` instead of the placeholder — more robust regardless of this specific change, since visible copy shouldn't be a test hook.
2. Any test asserting the literal text "DAAD Program Search" (currently none found, but re-check `App.test.tsx` during implementation) updates to "Study in Germany".

No new test *behavior* to cover — this isn't new functionality, so no new test cases beyond fixing the selector coupling above.

## Tech Stack

- No new runtime dependencies. One new asset dependency: Google Fonts (Inter), loaded via a `<link>` tag — free, no API key, no build-time dependency.
- Tailwind config gains `theme.extend.colors` and `theme.extend.fontFamily` — first customization of what's currently a fully default config.
