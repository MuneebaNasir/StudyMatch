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
