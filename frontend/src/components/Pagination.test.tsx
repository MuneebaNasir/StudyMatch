import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("renders nothing when every result already fits on one page", () => {
    const { container } = render(<Pagination offset={0} limit={20} total={15} onPageChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the current range and total", () => {
    render(<Pagination offset={20} limit={20} total={45} onPageChange={vi.fn()} />);
    expect(screen.getByText("Showing 21-40 of 45")).toBeInTheDocument();
  });

  it("disables Previous on the first page", () => {
    render(<Pagination offset={0} limit={20} total={45} onPageChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  it("disables Next on the last page", () => {
    render(<Pagination offset={40} limit={20} total={45} onPageChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
  });

  it("clicking Next advances by one page's worth of offset", async () => {
    const onPageChange = vi.fn();
    render(<Pagination offset={0} limit={20} total={45} onPageChange={onPageChange} />);
    await userEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(onPageChange).toHaveBeenCalledWith(20);
  });

  it("clicking Previous goes back by one page's worth of offset", async () => {
    const onPageChange = vi.fn();
    render(<Pagination offset={20} limit={20} total={45} onPageChange={onPageChange} />);
    await userEvent.click(screen.getByRole("button", { name: /previous/i }));
    expect(onPageChange).toHaveBeenCalledWith(0);
  });
});
