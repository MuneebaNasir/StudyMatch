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
  grade_value_on_german_scale?: number | null;
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

export interface EvaluateEligibilityResponse {
  eligibility_verdict: EligibilityVerdictValue;
  eligibility_reasoning: string | null;
}

export interface SubScore {
  section: string;
  min_score: number | null;
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
  min_score: string | null;
}

export interface LanguageRequirement {
  language: string;
  level: string | null;
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
