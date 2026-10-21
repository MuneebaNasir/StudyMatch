import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExtractionSummary } from "./ExtractionSummary";

describe("ExtractionSummary", () => {
  it("renders a removable chip per non-null filter field", () => {
    render(
      <ExtractionSummary
        filters={{ languages: ["English"], max_tuition_free_only: true, subject: null, city: null, course_type: null }}
        profile={null}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Languages: English")).toBeInTheDocument();
    expect(screen.getByText("Tuition-free only")).toBeInTheDocument();
  });

  it("renders a human-readable label for course type instead of the raw code", () => {
    render(
      <ExtractionSummary
        filters={{ languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: 2 }}
        profile={null}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Course type: Master's")).toBeInTheDocument();
    expect(screen.queryByText("Course type: 2")).not.toBeInTheDocument();
  });

  it("removing a filter chip calls onFiltersChange with that field nulled out", async () => {
    const onFiltersChange = vi.fn();
    render(
      <ExtractionSummary
        filters={{ languages: ["English"], max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={null}
        onFiltersChange={onFiltersChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /remove filter: languages: english/i }));

    expect(onFiltersChange).toHaveBeenCalledWith({
      languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null,
    });
  });

  it("renders profile fields as read-only chips with no remove control", () => {
    render(
      <ExtractionSummary
        filters={{ languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={{
          degree_field: "Artificial Intelligence", grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)",
          nationality: "Pakistan", other_notes: null,
        }}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Degree: Artificial Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Grade: 3.2 (4.0 GPA scale (USA))")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove.*degree/i })).not.toBeInTheDocument();
  });

  it("shows the German-scale equivalent in brackets when the backend provides one", () => {
    render(
      <ExtractionSummary
        filters={{ languages: null, max_tuition_free_only: null, subject: null, city: null, course_type: null }}
        profile={{
          degree_field: null, grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)",
          nationality: null, other_notes: null, grade_value_on_german_scale: 1.7,
        }}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Grade: 3.2 (4.0 GPA scale (USA)) [≈ 1.7 German scale]")).toBeInTheDocument();
  });

  it("shows a fallback notice when both filters and profile are null", () => {
    render(<ExtractionSummary filters={null} profile={null} onFiltersChange={vi.fn()} />);
    expect(screen.getByText(/couldn't extract structured details/i)).toBeInTheDocument();
  });

  it("renders a chip per completed course when courses are provided", () => {
    render(
      <ExtractionSummary
        filters={null}
        profile={null}
        courses={[{ name: "Linear Algebra", grade: "A" }, { name: "Data Structures", grade: null }]}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Linear Algebra (A)")).toBeInTheDocument();
    expect(screen.getByText("Data Structures")).toBeInTheDocument();
  });

  it("shows only the first two courses until the rest are expanded", async () => {
    const courses = Array.from({ length: 49 }, (_, i) => ({ name: `Course ${i + 1}`, grade: "A" }));
    render(<ExtractionSummary filters={null} profile={null} courses={courses} onFiltersChange={vi.fn()} />);

    expect(screen.getByText("Course 1 (A)")).toBeInTheDocument();
    expect(screen.getByText("Course 2 (A)")).toBeInTheDocument();
    expect(screen.queryByText("Course 3 (A)")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /\+47 more courses/i }));
    expect(screen.getByText("Course 49 (A)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /show fewer/i }));
    expect(screen.queryByText("Course 49 (A)")).not.toBeInTheDocument();
  });
});
