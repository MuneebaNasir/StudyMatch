import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatQueryBox } from "./ChatQueryBox";

describe("ChatQueryBox", () => {
  it("pre-fills the textarea with the Master's template on load", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[Master's]");
  });

  it("calls onSubmit with the trimmed query text", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "  bachelors in AI, CGPA 3.2  ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalledWith("bachelors in AI, CGPA 3.2");
  });

  it("does not call onSubmit for empty or whitespace-only input", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "   ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows loading copy while pending", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={true} />);
    expect(screen.getByRole("button", { name: /reading your profile/i })).toBeDisabled();
  });

  it("clicking the PhD example chip replaces the textarea content with the PhD template", async () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByRole("button", { name: /phd example/i }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[PhD]");
  });

  it("clicking the Bachelor's example chip replaces the textarea content with the Bachelor's template", async () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    await userEvent.click(screen.getByRole("button", { name: /bachelor's example/i }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("[Bachelor's]");
  });

  it("shows a caption above the textarea explaining it's an editable example", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect(screen.getByText(/example query — edit the details below/i)).toBeInTheDocument();
  });

  it("shows a label inviting the user to see more examples above the chips", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);
    expect(screen.getByText("Want to see more examples?")).toBeInTheDocument();
  });

  it("does not include the caption text in the submitted query", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalled();
    const submittedQuery = onSubmit.mock.calls[0][0] as string;
    expect(submittedQuery).not.toContain("Example query");
  });
});

describe("ChatQueryBox typing indicator", () => {
  beforeEach(() => {
    // shouldAdvanceTime: true (not just plain vi.useFakeTimers()) is required here:
    // @testing-library/react's asyncWrapper drains microtasks via a real setTimeout(0)
    // internally, but only detects and advances *Jest's* fake timers, not Vitest's. Without
    // shouldAdvanceTime, that setTimeout(0) is faked and never fires, and any `userEvent`
    // call (even with delay: null) hangs indefinitely. shouldAdvanceTime lets the fake
    // clock auto-advance in step with real time for that pending callback, while
    // vi.advanceTimersByTime() below still jumps the clock forward explicitly.
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the typing indicator while the user is actively typing, then fades it out after a pause", async () => {
    const user = userEvent.setup({ delay: null });
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={false} />);

    const textarea = screen.getByRole("textbox");
    await user.type(textarea, "a");

    expect(screen.getByText("🐌 typing...")).toHaveClass("opacity-100");

    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(screen.getByText("🐌 typing...")).toHaveClass("opacity-0");
  });
});
