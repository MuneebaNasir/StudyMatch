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

    const file = new File(["not a transcript"], "notes.txt", { type: "text/plain" });
    const input = screen.getByLabelText(/upload transcript/i);
    await userEvent.upload(input, file);

    await waitFor(() => expect(screen.getByText(/couldn't read this file/i)).toBeInTheDocument());
  });
});
