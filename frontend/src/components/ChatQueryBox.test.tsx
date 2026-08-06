import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatQueryBox } from "./ChatQueryBox";

describe("ChatQueryBox", () => {
  it("calls onSubmit with the trimmed query text", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.type(
      screen.getByPlaceholderText(/describe your background/i),
      "  bachelors in AI, CGPA 3.2  ",
    );
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).toHaveBeenCalledWith("bachelors in AI, CGPA 3.2");
  });

  it("does not call onSubmit for empty or whitespace-only input", async () => {
    const onSubmit = vi.fn();
    render(<ChatQueryBox onSubmit={onSubmit} isPending={false} />);

    await userEvent.type(screen.getByPlaceholderText(/describe your background/i), "   ");
    await userEvent.click(screen.getByRole("button", { name: /search programs/i }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the submit button and shows loading copy while pending", () => {
    render(<ChatQueryBox onSubmit={vi.fn()} isPending={true} />);

    expect(screen.getByRole("button", { name: /reading your profile/i })).toBeDisabled();
  });
});
