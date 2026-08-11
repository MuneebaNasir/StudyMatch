import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import App from "./App";
import { mswServer } from "./test/mswServer";

const API_BASE_URL = "http://localhost:8000";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

const QUERY_RESPONSE = {
  results: [
    {
      id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
      languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
      link: "https://example.com/1", score: 0.9, eligibility_verdict: "eligible",
      eligibility_reasoning: "Meets the grade threshold.",
    },
  ],
  total_matched: 1,
  extracted_filters: { languages: ["English"], max_tuition_free_only: null, subject: null, city: null, course_type: null },
  extracted_profile: {
    degree_field: "Robotics", grade_value: 3.2, grade_scale: "4.0 GPA scale (USA)", nationality: "Pakistan", other_notes: null,
  },
  semantic_query: "robotics",
};

describe("App", () => {
  it("submits a query, renders results, edits a chip to re-search, and opens the admission guide drawer", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, () => HttpResponse.json(QUERY_RESPONSE)),
      http.post(`${API_BASE_URL}/search`, async ({ request }) => {
        const body = (await request.json()) as { filters: Record<string, unknown>; semantic_query: string | null };
        expect(body.filters.languages).toBeNull();
        expect(body.semantic_query).toBe("robotics");
        return HttpResponse.json({
          results: [{
            id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
            languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
            link: "https://example.com/1", score: 0.9,
          }],
          total_matched: 1,
        });
      }),
      http.get(`${API_BASE_URL}/programs/1`, () =>
        HttpResponse.json({
          id: 1, course_name: "Robotics Engineering MSc", university: "TU Berlin", city: "Berlin",
          languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
          link: "https://example.com/1", score: 0.9, course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: { admission_requirements: "A grade of 2.5 or better is required." }, structured_eligibility: null,
        }),
      ),
    );

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters, English taught");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.getByText("Languages: English")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /remove filter: languages: english/i }));

    await waitFor(() => expect(screen.queryByText("Languages: English")).not.toBeInTheDocument());
    expect(screen.getByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Robotics Engineering MSc"));

    await userEvent.click(await screen.findByRole("button", { name: /requirements & language/i }));
    expect(await screen.findByText(/a grade of 2.5 or better is required/i)).toBeInTheDocument();
    expect(
      within(screen.getByText("Eligibility").parentElement as HTMLElement).getByText(/meets the grade threshold/i),
    ).toBeInTheDocument();
  });

  it("pages through results when there are more than fit on one page", async () => {
    function makeResults(count: number, offset: number) {
      return Array.from({ length: count }, (_, i) => ({
        id: offset + i + 1, course_name: `Course ${offset + i + 1}`, university: "TU X", city: null,
        languages: ["English"], subject: null, tuition_fees_text: null, application_deadline_text: null,
        link: "https://example.com", score: null, eligibility_verdict: "no_data" as const, eligibility_reasoning: null,
      }));
    }

    let lastOffset = -1;
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = (await request.json()) as { offset: number };
        lastOffset = body.offset;
        return HttpResponse.json({
          results: makeResults(20, body.offset),
          total_matched: 45,
          extracted_filters: null,
          extracted_profile: null,
          semantic_query: null,
        });
      }),
    );

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText("Showing 1-20 of 45")).toBeInTheDocument();
    expect(screen.getByText("Course 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => expect(lastOffset).toBe(20));
    expect(await screen.findByText("Showing 21-40 of 45")).toBeInTheDocument();
    expect(screen.getByText("Course 21")).toBeInTheDocument();
    expect(screen.queryByText("Course 1")).not.toBeInTheDocument();
  });

  it("retry after a failed query re-fires the request and renders results on success", async () => {
    let callCount = 0;
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, () => {
        callCount += 1;
        if (callCount === 1) {
          return HttpResponse.json(null, { status: 500 });
        }
        return HttpResponse.json(QUERY_RESPONSE);
      }),
    );

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument();
    expect(callCount).toBe(2);
  });

  it("start over resets the query, chips, results, and closes the drawer", async () => {
    mswServer.use(http.post(`${API_BASE_URL}/query`, () => HttpResponse.json(QUERY_RESPONSE)));

    renderApp();

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "robotics masters");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));
    expect(await screen.findByText("Robotics Engineering MSc")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /start over/i }));

    expect(screen.queryByText("Robotics Engineering MSc")).not.toBeInTheDocument();
    expect(screen.queryByText(/start over/i)).not.toBeInTheDocument();
  });
});
