import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Header } from "./Header";

describe("Header", () => {
  it("renders the site name and welcoming tagline", () => {
    render(<Header />);
    expect(screen.getByRole("heading", { name: "Study in Germany" })).toBeInTheDocument();
    expect(
      screen.getByText("Your international student counselor for German universities."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Write your query below and I'll find the right program for you."),
    ).toBeInTheDocument();
  });
});
