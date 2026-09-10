import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { mswServer } from "../test/mswServer";
import { getProgram, postQuery, postSearch, postTranscript } from "./client";

const API_BASE_URL = "http://localhost:8000";

describe("api client", () => {
  it("postQuery sends the query, offset, and limit, and returns the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ query: "robotics masters", offset: 0, limit: 20, session_token: null });
        return HttpResponse.json({
          results: [], total_matched: 0, extracted_filters: null, extracted_profile: null, semantic_query: null,
        });
      }),
    );

    const result = await postQuery("robotics masters");
    expect(result.total_matched).toBe(0);
  });

  it("postQuery sends a non-zero offset when paginating", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ query: "robotics masters", offset: 20, limit: 20, session_token: null });
        return HttpResponse.json({
          results: [], total_matched: 0, extracted_filters: null, extracted_profile: null, semantic_query: null,
        });
      }),
    );

    await postQuery("robotics masters", 20);
  });

  it("postSearch sends filters, semantic_query, and offset, and returns the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/search`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({
          filters: { languages: ["English"] }, semantic_query: "robotics", offset: 0, limit: 20,
        });
        return HttpResponse.json({ results: [], total_matched: 0 });
      }),
    );

    const result = await postSearch({ languages: ["English"] }, "robotics");
    expect(result.total_matched).toBe(0);
  });

  it("postSearch sends a non-zero offset when paginating", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/search`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({
          filters: { languages: ["English"] }, semantic_query: "robotics", offset: 20, limit: 20,
        });
        return HttpResponse.json({ results: [], total_matched: 0 });
      }),
    );

    await postSearch({ languages: ["English"] }, "robotics", 20);
  });

  it("getProgram fetches a program by id", async () => {
    mswServer.use(
      http.get(`${API_BASE_URL}/programs/10396`, () =>
        HttpResponse.json({
          id: 10396, course_name: "Additive Manufacturing", university: "TU X", city: null,
          languages: ["English"], subject: null, tuition_fees_text: null,
          application_deadline_text: null, link: "https://example.com", score: null,
          course_type: 2, degree: null, duration: null, beginning: null,
          raw_sections: {}, structured_eligibility: null,
        }),
      ),
    );

    const result = await getProgram(10396);
    expect(result.course_name).toBe("Additive Manufacturing");
  });

  it("throws when the response is not ok", async () => {
    mswServer.use(
      http.get(`${API_BASE_URL}/programs/999`, () => new HttpResponse(null, { status: 404 })),
    );

    await expect(getProgram(999)).rejects.toThrow("GET /programs/999 failed with 404");
  });

  it("postQuery sends the session_token when provided", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ query: "robotics masters", offset: 0, limit: 20, session_token: "abc123" });
        return HttpResponse.json({
          results: [], total_matched: 0, extracted_filters: null, extracted_profile: null,
          extracted_courses: null, semantic_query: null,
        });
      }),
    );

    await postQuery("robotics masters", 0, 20, "abc123");
  });

  it("postTranscript uploads a file and returns the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/transcript`, () =>
        HttpResponse.json({
          session_token: "abc123", courses: [{ name: "Linear Algebra", grade: "A" }],
          grade_value: 3.8, grade_scale: "4.0 GPA", nationality: "Pakistan",
          degree_field: "Computer Science", extraction_confidence: "high",
        }),
      ),
    );

    const file = new File([new Blob(["fake pdf bytes"])], "transcript.pdf", { type: "application/pdf" });
    const result = await postTranscript(file);

    expect(result.session_token).toBe("abc123");
    expect(result.courses[0].name).toBe("Linear Algebra");
  });
});
