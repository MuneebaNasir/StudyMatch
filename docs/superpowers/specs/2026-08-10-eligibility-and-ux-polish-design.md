# Eligibility Cost Control & UX Polish — Design

## Context

The app (spec history: `2026-08-06-frontend-design.md`, `2026-08-07-frontend-redesign-design.md`) is live in production (Vercel + Cloud Run + Neon + Qdrant Cloud). Real usage surfaced five issues worth fixing before wider use:

1. Eligibility reasoning currently runs automatically for the top 10 results of every `/query` call that includes a student profile — this is the single biggest driver of LLM token cost (~4,932 tokens per call, per real measurement), and Groq's free daily budget only covers ~25-30 such queries before falling back to Mistral.
2. The admission guide drawer's "Original program details" section is a flat, unorganized dump of raw text.
3. New users don't know what a good query looks like — no examples or guidance in the UI at all.
4. `degree_prerequisite.description` and `.source_quote` are byte-for-byte identical text in 932/1891 (49%) of extracted programs, and the UI renders both — the same sentence visibly duplicated, once bold and once as a smaller quote underneath.
5. The profile chip shows a student's self-reported grade in their own scale (e.g. "3.2, 4.0 GPA scale (USA)") with no German-scale equivalent shown, even though the backend already computes this deterministically for its own internal reasoning prompt — just never surfaces it.

This spec covers all five, decided through direct conversation with the user (grouped here because they're all small, are all frontend-visible, and several touch the same components).

## Goal

Cut the automatic eligibility cost by 80% while keeping every program's eligibility reachable on demand; make the admission guide's raw content genuinely browsable; give users a concrete, editable example of what to ask instead of a blank box; stop showing the same sentence twice; and show a real German-scale grade equivalent using logic the backend already has.

## Scope

**In scope:** all five items below, end to end (backend + frontend where applicable).

**Explicitly out of scope:**
- True per-field "mad-libs" ghost-text inputs (multiple inline `<input>`s within a sentence) — using pre-filled real editable text instead, per explicit user decision (simpler to build, ~90% of the benefit)
- Any change to the extraction pipeline itself (the `degree_prerequisite` duplication is a *display* fix, not a re-extraction — re-extracting 1891 programs to stop the LLM from ever duplicating text isn't worth the cost for a cosmetic issue)
- Any change to which grading scales `convert_to_german_scale` recognizes (percentage / CGPA-10 / GPA-4 only, per existing code) — just exposing its existing output, not extending it

---

## Feature 1: Eligibility — top 2 automatic, button for the rest

**Backend (`src/daad_search/api/query.py`):**
- `REASONING_CANDIDATE_CAP` changes from `10` to `2` (line 16). This is the only change to the automatic path — everything else in `handle_query` (the `no_data`/`unclear` fallback logic for results outside the pool) already works correctly for any cap value.

**New endpoint** for on-demand single-program evaluation, in `src/daad_search/api/main.py`:

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

This mirrors `handle_query`'s existing `no_data`/`unclear` fallback pattern exactly (same two edge cases: no structured eligibility data at all, or the LLM call failing) rather than inventing new fallback semantics.

**Frontend (`AdmissionGuideDrawer.tsx`):** where `verdict.eligibility_reasoning ?? "No reasoning available."` currently renders (line 56):
- If `verdict.eligibility_verdict === "no_data"` **and** a profile exists (`extracted_profile` has at least one non-null field): show an **"Evaluate eligibility"** button instead of the reasoning text. Clicking it calls the new endpoint with the current query's profile, shows a loading state, then updates to show the real verdict badge + reasoning — replacing the "Not evaluated" badge and button with the real result.
- If `verdict.eligibility_verdict === "no_data"` **and no profile exists at all**: show a plain message — "Add your background to the search box to check eligibility" — instead of a button that could never produce a real result.
- Otherwise (a real verdict, from either the automatic top-2 or a previous on-demand evaluation): unchanged, shows reasoning text as today.

**State flow:** `AdmissionGuideDrawer` currently receives a `verdict` prop but not the underlying profile or a way to report a new one back up. Two new props are needed:
- `profile: StudentProfile | null` — `App.tsx` already holds this as `queryResponse.extracted_profile` (currently passed to `ExtractionSummary` only); wire the same value into `AdmissionGuideDrawer` too, so the drawer can send it in the `evaluate-eligibility` request body.
- `onEligibilityEvaluated: (programId: number, verdict: EligibilityVerdictValue, reasoning: string | null) => void` — called after a successful on-demand evaluation. `App.tsx`'s handler updates the same `verdictMap` state that already drives both the drawer and the results-list cards, so a successful evaluation updates both places from one state update, not two.

## Feature 2: Original program details → organized dropdowns

Replace the flat `RawAdmissionText` rendering with four collapsible sections (Radix `Accordion`, matching the existing Radix `Dialog` used for the drawer itself — same library already a dependency), each closed by default:

| Section | Raw field(s) |
|---|---|
| **Overview** | `description` |
| **Course Details** | `degree` |
| **Costs & Deadlines** | `tuition_fees`, `application_deadline` |
| **Requirements & Language** | `admission_requirements`, `german_language`, `english_language` |

A section is omitted entirely if none of its fields have non-empty values (matches the existing `RawAdmissionText` behavior of skipping empty fields, just at the section level too). The "Original program details" heading itself becomes visually stronger (bolder/larger) to read clearly as a distinct section from the structured eligibility summary above it, per the user's explicit note that it currently doesn't stand out enough.

## Feature 3: Query hints — pre-filled template + degree-level chips

**`ChatQueryBox.tsx`:**
- The textarea's initial state is no longer `""` — it's pre-filled with the Master's template (below), visible the moment the page loads, no click required:

  > I am looking for a [Master's] program in [AI, agentic AI, and large language models], taught in [English], with [no tuition fees], near [Berlin].
  >
  > I have a [Bachelor's degree in Computer Science] with a [3.2 GPA on a 4.0 scale] from [Pakistan], and an [IELTS score of 7.0].

- Two chips beneath the box: **"PhD example"** and **"Bachelor's example"**. Clicking one replaces the box's entire content with that degree level's template:

  **PhD:**
  > I am looking for a [PhD] position in [machine learning and natural language processing], taught in [English], with [no tuition fees], near [Munich].
  >
  > I have a [Master's degree in Computer Science] with a [1.7 grade on the German scale] from [Nigeria], [2 years of research experience in NLP], and an [IELTS score of 7.5].

  **Bachelor's:**
  > I am looking for a [Bachelor's] program in [computer science or data science], taught in [English], with [no tuition fees], near [Hamburg].
  >
  > I completed [high school / Abitur-equivalent] with a [grade of 85%] in [India], and an [IELTS score of 6.5].

- All template text is real, editable textarea content (not a native `placeholder` attribute) — the bracketed words are meant to be selected and replaced by the user, not auto-clearing ghost text. This is the deliberately simpler alternative to true per-field mad-libs inputs, per explicit user decision.
- If a user submits without editing the brackets at all, the query still gets sent as-is (no validation blocking submission) — the LLM parser handles it reasonably in practice, and adding strict validation for this edge case is unnecessary complexity for what's a self-correcting affordance (the bracket text itself signals "replace me").

## Feature 4: Duplicate text fix

In `AdmissionGuideDrawer.tsx`'s `RequirementRow`, don't render the quote block when it's identical to the label:

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

This is a single change point covering every caller of `RequirementRow` (`grade_requirement`, `language_requirements`, `standardized_tests`, `degree_prerequisite`) — fixes the 932-program `degree_prerequisite` case and the rare 20-case `language_requirements` overlap identically, without special-casing either field.

## Feature 5: German grade-scale equivalent

**Backend:** `StudentProfile` (`query_understanding/schema.py`) gains a new field:

```python
class StudentProfile(BaseModel):
    degree_field: str | None = None
    grade_value: float | None = None
    grade_scale: str | None = None
    nationality: str | None = None
    other_notes: str | None = None
    grade_value_on_german_scale: float | None = None
```

Populated in `handle_query` (`api/query.py`) immediately after `parse_query` returns, using the **existing** `convert_to_german_scale` function from `reasoner.py` (no new conversion logic — reuses the exact function already used internally for the reasoning prompt):

```python
if profile is not None and profile.grade_value is not None:
    profile.grade_value_on_german_scale = convert_to_german_scale(profile.grade_value, profile.grade_scale)
```

Stays `None` when the scale isn't one of the three the function recognizes (percentage / CGPA-10 / GPA-4) — same "don't guess" behavior the function already has, not a new failure mode to handle.

**Frontend (`ExtractionSummary.tsx`):** the grade chip changes from:
```
Grade: 3.2 (4.0 GPA scale (USA))
```
to, when a conversion is available:
```
Grade: 3.2 (4.0 GPA scale (USA)) [≈ 1.7 German scale]
```
and stays as it is today (no bracket) when `grade_value_on_german_scale` is `null`.

## Testing

Following this project's established pattern (component-level Vitest/RTL tests for the frontend with MSW-stubbed endpoints, pytest for the backend, TDD throughout):

- **Feature 1:** backend test for `evaluate-eligibility`'s three response shapes (real verdict, `no_data` when no structured eligibility exists, `unclear` when reasoning fails) mirroring the existing `test_query_api.py` patterns; frontend test that the button appears only when `no_data` + a profile exists, the prompt message appears when `no_data` + no profile, and clicking the button updates both the drawer and (via the callback) the results-list card.
- **Feature 2:** test that each section renders only when it has at least one non-empty field, and that all four sections' content matches their assigned raw fields.
- **Feature 3:** test that the textarea's initial value is the Master's template, and that clicking each chip replaces it with the correct template.
- **Feature 4:** test that `RequirementRow` omits the quote block when identical to the label, and still shows it when they differ (regression coverage for the working case).
- **Feature 5:** backend test that `grade_value_on_german_scale` is populated for a recognized scale and stays `null` for an unrecognized one (reusing `reasoner.py`'s own already-tested `convert_to_german_scale`, so this is really just testing the wiring, not the math again); frontend test that the chip shows the bracketed conversion when present and omits it when `null`.
