import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "../App";

const models = {
  default_model_id: "gpt-5.5",
  models: [
    { model_id: "gpt-5.5", display_name: "Deterministic fixture — GPT-5.5 contract", subtitle: null, availability: "available", disabled_reason: null, adapter_type: "responses", execution_mode: "fixture", actual_adapter_type: "fixture", configured_model_name: "internal-package-derived-fixture", structured_output_capability: "validated", reasoning_capability: true, configuration_digest: "a".repeat(64), network_required: false },
    { model_id: "qwen3.6-local", display_name: "Qwen 3.6 local — coming soon", subtitle: "27B Dense / 35B-A3B", availability: "coming_soon", disabled_reason: "Not validated.", adapter_type: "chat_completions", execution_mode: "disabled", actual_adapter_type: null, configured_model_name: null, structured_output_capability: "unvalidated", reasoning_capability: true, configuration_digest: "b".repeat(64), network_required: true },
  ],
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("makes upload analysis primary and keeps Qwen disabled without benchmark metrics", async () => {
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
  expect(await screen.findByRole("option", { name: /Qwen 3.6 local/i })).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I confirm this target context/i));
  expect(screen.getByRole("button", { name: "Parse and analyze" })).toBeEnabled();
});
