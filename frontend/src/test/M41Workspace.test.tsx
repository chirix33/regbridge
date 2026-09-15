import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "../App";

import fixture from "./fixtures/m43-product.json";
const models = fixture.configuration;

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("makes upload analysis primary and uses read-only server configuration without benchmark metrics", async () => {
  window.history.pushState({}, "", "/");
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(models), { status: 200, headers: { "Content-Type": "application/json" } }))));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Analyze a dossier" })).toBeVisible();
  expect(screen.getByText(/Forward compatibility is currently unavailable/i)).toBeVisible();
  expect(screen.getByText(/Not validated by a regulatory expert/i)).toBeVisible();
  expect(screen.queryByText(/macro-F1|unsafe-FNR|accuracy/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try a sample dossier" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Open navigation menu" })).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(screen.getByRole("button", { name: "Open navigation menu" }));
  expect(screen.getByRole("button", { name: "Close navigation menu" })).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(screen.getByRole("button", { name: "Close navigation menu" }));
  expect(screen.getByRole("button", { name: "Open navigation menu" })).toHaveAttribute("aria-expanded", "false");
  const input = screen.getByLabelText("Dossier ZIP");
  fireEvent.change(input, { target: { files: [new File(["zip"], "synthetic.zip", { type: "application/zip" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to options" }));
  expect(await screen.findByText("Offline demonstration")).toBeVisible();
  expect(screen.queryByLabelText("Analysis model")).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/I confirm this target context/i));
  expect(screen.getByRole("button", { name: "Parse and analyze" })).toBeEnabled();
});
