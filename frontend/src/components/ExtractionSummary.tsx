import type { SearchFilters, StudentProfile } from "../types";

interface FilterChip {
  key: keyof SearchFilters;
  label: string;
}

// Mirrors the DAAD course type codes documented in
// src/daad_search/query_understanding/parser.py's extraction prompt.
const COURSE_TYPE_LABELS: Record<number, string> = {
  1: "Bachelor's",
  2: "Master's",
  3: "PhD",
  4: "Graduate school",
  5: "Language course",
  6: "Short course",
  7: "Preparatory course",
  9: "Various",
};

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
    const label = COURSE_TYPE_LABELS[filters.course_type] ?? `Unknown (${filters.course_type})`;
    chips.push({ key: "course_type", label: `Course type: ${label}` });
  }
  return chips;
}

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

interface ExtractionSummaryProps {
  filters: SearchFilters | null;
  profile: StudentProfile | null;
  onFiltersChange: (filters: SearchFilters) => void;
}

export function ExtractionSummary({ filters, profile, onFiltersChange }: ExtractionSummaryProps) {
  if (filters === null && profile === null) {
    return (
      <p className="text-sm text-ink/70">
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
          className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-3 py-1 text-xs text-ink"
        >
          {chip.label}
          <button
            type="button"
            aria-label={`Remove filter: ${chip.label}`}
            onClick={() => removeFilterChip(chip.key)}
            className="ml-1 text-ink/40 hover:text-ink"
          >
            ×
          </button>
        </span>
      ))}
      {profileChips.map((label) => (
        <span
          key={label}
          className="inline-flex items-center rounded-full bg-line/40 px-3 py-1 text-xs text-ink/70"
        >
          {label}
        </span>
      ))}
    </div>
  );
}
