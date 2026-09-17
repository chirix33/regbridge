import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import App from "../App";
it("keeps About concise and primary navigation limited to product workspaces", () => {
  window.history.pushState({}, "", "/about");
  render(<App/>);
  expect(screen.getByRole("heading", { name: "About RegBridge" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Check pinned standards" })).toBeVisible();
  const nav = screen.getByRole("navigation");
  expect(within(nav).getByRole("link", { name: "Analyzer" })).toBeVisible();
  expect(within(nav).queryByRole("link", { name: "Evaluation" })).toBeNull();
  expect(within(nav).queryByRole("link", { name: "Guided cases" })).toBeNull();
  expect(screen.queryByText(/SHA-256|Source-verified registry/)).toBeNull();
});
