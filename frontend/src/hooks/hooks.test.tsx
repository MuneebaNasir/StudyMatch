import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { PropsWithChildren } from "react";
import { describe, expect, it } from "vitest";

import { mswServer } from "../test/mswServer";
import { useFilteredSearch } from "./useFilteredSearch";
import { useProgramDetail } from "./useProgramDetail";
import { useQuerySearch } from "./useQuerySearch";

const API_BASE_URL = "http://localhost:8000";

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useQuerySearch", () => {
  it("posts the query and exposes the result via mutateAsync", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/query`, () =>
        HttpResponse.json({
          results: [], total_matched: 3, extracted_filters: null, extracted_profile: null, semantic_query: null,
        }),
      ),
    );
    const { result } = renderHook(() => useQuerySearch(), { wrapper });

    const response = await result.current.mutateAsync("robotics masters");
    expect(response.total_matched).toBe(3);
  });
});

describe("useFilteredSearch", () => {
  it("posts filters and exposes the result via mutateAsync", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/search`, () => HttpResponse.json({ results: [], total_matched: 1 })),
    );
    const { result } = renderHook(() => useFilteredSearch(), { wrapper });

    const response = await result.current.mutateAsync({
      filters: { languages: ["English"] }, semanticQuery: null,
    });
    expect(response.total_matched).toBe(1);
  });
});

describe("useProgramDetail", () => {
  it("does not fetch when programId is null", () => {
    const { result } = renderHook(() => useProgramDetail(null), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });

  it("fetches the program when programId is set", async () => {
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
    const { result } = renderHook(() => useProgramDetail(10396), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.course_name).toBe("Additive Manufacturing");
  });
});
