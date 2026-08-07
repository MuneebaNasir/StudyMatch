import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "./Header";

describe("Header", () => {
  it("renders the site name and tagline", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { name: "Study in Germany" })).toBeInTheDocument();
    expect(
      screen.getByText("Your international student counselor for study programmes in Germany"),
    ).toBeInTheDocument();
  });
});
