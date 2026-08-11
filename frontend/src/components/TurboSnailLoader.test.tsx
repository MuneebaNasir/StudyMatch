import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TurboSnailLoader } from "./TurboSnailLoader";

describe("TurboSnailLoader", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the first stage's text immediately on mount", () => {
    render(<TurboSnailLoader />);
    expect(screen.getByText("Waking up the server...")).toBeInTheDocument();
  });

  it("advances to the second stage's text after 2 seconds", () => {
    render(<TurboSnailLoader />);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("Reading your query...")).toBeInTheDocument();
  });

  it("advances to the third stage's text after 4 seconds", () => {
    render(<TurboSnailLoader />);
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.getByText("Matching programs...")).toBeInTheDocument();
  });
});
