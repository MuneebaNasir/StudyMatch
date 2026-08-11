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

  it("falls back to raw_sections when structured_eligibility is null", async () => {
    renderDrawer({
      program: { ...BASE_PROGRAM, raw_sections: { admission_requirements: "A bachelor's degree with a grade of 2.5 or better." } },
    });
    await userEvent.click(screen.getByRole("button", { name: /requirements & language/i }));
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

  const PROGRAM_WITH_ELIGIBILITY_DATA: ProgramDetail = {
    ...BASE_PROGRAM,
    structured_eligibility: {
      requires_gre: null, requires_gmat: null, min_german_level: null, min_english_level: null,
      extraction_confidence: "high", degree_prerequisite: null, grade_requirement: null,
      standardized_tests: [], language_requirements: [], notes: null,
    },
  };

  it("shows an 'Evaluate eligibility' button when the verdict is no_data, a profile exists, and the program has eligibility data", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: { nationality: "Pakistan" },
      program: PROGRAM_WITH_ELIGIBILITY_DATA,
    });
    expect(screen.getByRole("button", { name: /evaluate eligibility/i })).toBeInTheDocument();
  });

  it("shows a prompt to add background instead of a button when the verdict is no_data and there is no profile", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: null,
      program: PROGRAM_WITH_ELIGIBILITY_DATA,
    });
    expect(screen.queryByRole("button", { name: /evaluate eligibility/i })).not.toBeInTheDocument();
    expect(screen.getByText(/add your background to the search box to check eligibility/i)).toBeInTheDocument();
  });

  it("does not show the 'Evaluate eligibility' button when the program has no eligibility data, even with a profile", () => {
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: { nationality: "Pakistan" },
      program: BASE_PROGRAM, // structured_eligibility: null
    });
    expect(screen.queryByRole("button", { name: /evaluate eligibility/i })).not.toBeInTheDocument();
    expect(screen.getByText(/this program doesn't have eligibility data/i)).toBeInTheDocument();
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
      program: PROGRAM_WITH_ELIGIBILITY_DATA,
      onEligibilityEvaluated,
    });

    await userEvent.click(screen.getByRole("button", { name: /evaluate eligibility/i }));

    await waitFor(() =>
      expect(onEligibilityEvaluated).toHaveBeenCalledWith(10396, "eligible", "Meets all requirements."),
    );
  });

  it("shows an error message when evaluating eligibility fails", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/programs/10396/evaluate-eligibility`, () =>
        HttpResponse.json(null, { status: 500 }),
      ),
    );
    renderDrawer({
      verdict: { eligibility_verdict: "no_data", eligibility_reasoning: null },
      profile: { nationality: "Pakistan" },
      program: PROGRAM_WITH_ELIGIBILITY_DATA,
    });

    await userEvent.click(screen.getByRole("button", { name: /evaluate eligibility/i }));

    await waitFor(() =>
      expect(screen.getByText(/couldn't evaluate eligibility/i)).toBeInTheDocument(),
    );
  });

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
});
