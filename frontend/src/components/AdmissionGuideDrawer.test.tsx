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

  it("renders a link to the program's DAAD page", () => {
    render(
      <AdmissionGuideDrawer
        programId={10396} verdict={null} isLoading={false} isError={false} onClose={vi.fn()}
        program={{ ...BASE_PROGRAM, link: "https://www2.daad.de/program/10396" }}
      />,
    );
    const link = screen.getByRole("link", { name: /view program page/i });
    expect(link).toHaveAttribute("href", "https://www2.daad.de/program/10396");
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

  it("renders the verdict badge and label when a verdict is provided", () => {
    render(
      <AdmissionGuideDrawer
        programId={10396}
        verdict={{ eligibility_verdict: "eligible", eligibility_reasoning: "Meets the grade threshold." }}
        isLoading={false}
        isError={false}
        onClose={vi.fn()}
        program={BASE_PROGRAM}
      />,
    );
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByText(/meets the grade threshold/i)).toBeInTheDocument();
  });

  it("renders a null language level as 'no minimum level required', not the literal word null", () => {
    render(
      <AdmissionGuideDrawer
        programId={10396} verdict={null} isLoading={false} isError={false} onClose={vi.fn()}
        program={{
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
        }}
      />,
    );
    expect(screen.getByText(/german: no minimum level required/i)).toBeInTheDocument();
    expect(screen.queryByText(/german: null/i)).not.toBeInTheDocument();
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
