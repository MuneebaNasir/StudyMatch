import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

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
