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
