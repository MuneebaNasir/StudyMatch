import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";

import { mswServer } from "../test/mswServer";
import { TranscriptUpload } from "./TranscriptUpload";

const API_BASE_URL = "http://localhost:8000";

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("TranscriptUpload", () => {
  it("uploads the selected file and calls onUploaded with the parsed response", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/transcript`, () =>
        HttpResponse.json({
          session_token: "abc123", courses: [{ name: "Linear Algebra", grade: "A" }],
          grade_value: 3.8, grade_scale: "4.0 GPA", nationality: "Pakistan",
          degree_field: "Computer Science", extraction_confidence: "high",
        }),
      ),
    );
    const onUploaded = vi.fn();
    render(<TranscriptUpload onUploaded={onUploaded} />, { wrapper });

    const file = new File(["fake pdf bytes"], "transcript.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText(/upload transcript/i);
    await userEvent.upload(input, file);

    await waitFor(() =>
      expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ session_token: "abc123" })),
    );
  });

  it("shows an error message when the upload fails", async () => {
    mswServer.use(http.post(`${API_BASE_URL}/transcript`, () => new HttpResponse(null, { status: 415 })));
    render(<TranscriptUpload onUploaded={vi.fn()} />, { wrapper });

    const file = new File(["not a transcript"], "corrupt.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText(/upload transcript/i);
    await userEvent.upload(input, file);

    await waitFor(() => expect(screen.getByText(/couldn't read this file/i)).toBeInTheDocument());
  });

  it("shows a low-confidence message instead of the success state when extraction found nothing", async () => {
    mswServer.use(
      http.post(`${API_BASE_URL}/transcript`, () =>
        HttpResponse.json({
          session_token: "abc123", courses: [],
          grade_value: null, grade_scale: null, nationality: null,
          degree_field: null, extraction_confidence: "low",
        }),
      ),
    );
    const onUploaded = vi.fn();
    render(<TranscriptUpload onUploaded={onUploaded} />, { wrapper });

    const file = new File(["fake pdf bytes"], "blurry.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText(/upload transcript/i);
    await userEvent.upload(input, file);

    // The session token must still be stored -- a low-confidence, zero-course
    // upload is still valid state -- but it must not be celebrated as loaded.
    await waitFor(() =>
      expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ session_token: "abc123" })),
    );
    expect(screen.getByText(/couldn't read this file clearly/i)).toBeInTheDocument();
    expect(screen.queryByText(/transcript loaded/i)).not.toBeInTheDocument();
  });
});
