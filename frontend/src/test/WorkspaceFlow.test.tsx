import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { DossierWorkspace } from "../pages/DossierWorkspace";
import { BaselinesWorkspace } from "../pages/BaselinesWorkspace";
import { parseUpload } from "../api/client";

const catalog = { models: [{ model_id: "gpt-5.5", display_name: "Offline sample", availability: "available", execution_mode: "fixture", network_required: false }, { model_id: "second-model", display_name: "Second model", availability: "available", execution_mode: "fixture", network_required: false }] };
const inventory = { id: "inv-one", leaves: [{ id: "leaf-one", title: "Structure document", policy_coverage_status: "EVALUATED_WITH_APPROVED_POLICY" }] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function mount(comparison = false) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{comparison ? <BaselinesWorkspace/> : <DossierWorkspace/>}</MemoryRouter></QueryClientProvider>);
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("replaces setup with the loader and restores editable inputs after a rejected upload", async () => {
  let resolveUpload!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/models") ? Promise.resolve(json(catalog)) : new Promise<Response>((resolve) => { resolveUpload = resolve; })));
  mount();
  fireEvent.change(screen.getByLabelText("Dossier ZIP"), { target: { files: [new File(["bad"], "invalid.zip")] } });
  fireEvent.click(screen.getByRole("button", { name: "Continue to options" }));
  await screen.findByRole("option", { name: "Offline sample" });
  fireEvent.click(screen.getByLabelText(/I confirm/));
  fireEvent.click(screen.getByRole("button", { name: "Parse and analyze" }));
  expect(screen.getByRole("status")).toHaveTextContent("Checking your package");
  expect(screen.queryByLabelText("Dossier ZIP")).not.toBeInTheDocument();
  expect(screen.queryByText("Package summary")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to home" })).toBeVisible();
  act(() => resolveUpload(json({ detail: "Missing index.xml" }, 422)));
  expect(await screen.findByRole("alert")).toHaveTextContent("Check the dossier");
  expect(screen.getByRole("alert")).toHaveTextContent("Missing index.xml");
  expect(screen.getByText("Selected: invalid.zip")).toBeVisible();
  expect(screen.getByRole("button", { name: "Parse and analyze" })).toBeEnabled();
});

it("submits the selected comparison model, recovers polling without restarting, and focuses results", async () => {
  sessionStorage.setItem("regbridge.inventory", JSON.stringify(inventory));
  let polls = 0;
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith("/models")) return Promise.resolve(json(catalog));
    if (options?.method === "POST") return Promise.resolve(json({ comparison_id: "run-one", state: "running", results: [] }));
    polls += 1;
    if (polls === 1) return Promise.reject(new TypeError("Failed to fetch"));
    return Promise.resolve(json({ comparison_id: "run-one", state: "completed", results: [], failures: [] }));
  });
  vi.stubGlobal("fetch", fetchMock);
  mount(true);
  await screen.findByRole("option", { name: "Second model" });
  fireEvent.change(screen.getByLabelText("Analysis model"), { target: { value: "second-model" } });
  fireEvent.click(screen.getByRole("button", { name: "Run comparison" }));
  expect(screen.getByRole("status")).toHaveTextContent("Running the comparison");
  expect(screen.queryByLabelText("Analysis model")).not.toBeInTheDocument();
  await screen.findByRole("button", { name: "Check status again" });
  fireEvent.click(screen.getByRole("button", { name: "Check status again" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Your comparison results" })).toHaveFocus());
  const submissions = fetchMock.mock.calls.filter(([, options]) => options?.method === "POST");
  expect(submissions).toHaveLength(1);
  expect(JSON.parse(submissions[0]?.[1]?.body as string)).toMatchObject({ model_id: "second-model", leaf_ids: ["leaf-one"] });
  fireEvent.click(screen.getByRole("button", { name: "Edit setup" }));
  expect(screen.getByLabelText("Analysis model")).toHaveValue("second-model");
});

it("requires reading a newly selected ZIP before comparing a previous inventory", async () => {
  sessionStorage.setItem("regbridge.inventory", JSON.stringify(inventory));
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(catalog))));
  mount(true);
  await screen.findByRole("option", { name: "Offline sample" });
  expect(screen.getByRole("button", { name: "Run comparison" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Change dossier" }));
  fireEvent.change(screen.getByLabelText("Comparison dossier ZIP"), { target: { files: [new File(["zip"], "new.zip")] } });
  expect(screen.queryByRole("button", { name: "Run comparison" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Read document list" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Keep the previous dossier" }));
  expect(screen.getByRole("button", { name: "Run comparison" })).toBeEnabled();
});

it("handles structured validation errors without exposing object serialization", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: [{ loc: ["body"], msg: "invalid" }] }, 422))));
  await expect(parseUpload(new File(["zip"], "test.zip"))).rejects.toThrow("Check the dossier and try again");
});
