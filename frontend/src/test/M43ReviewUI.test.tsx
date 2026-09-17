import { useState } from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApplicationInventory, ComparisonRun, DossierAnalysisRun } from "../api/contracts";
import fixture from "./fixtures/m43-product.json";
import { comparisonDocument, documentReviewItems, dossierDocuments, groupReviewItems, projectDocument } from "../api/presentation";
import { defaultTarget, savedTarget } from "../api/targetSetup";
import { DossierPicker } from "../components/DossierPicker";
import { ConfigurationDisclosure, ProductSetup } from "../components/ProductSetup";
import { DocumentReview } from "../components/ReviewWorkspace";

const inventory = fixture.inventory as ApplicationInventory;
const completed = dossierDocuments(inventory, fixture.run as DossierAnalysisRun);
const abstained = dossierDocuments(inventory, fixture.abstention as DossierAnalysisRun);
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

describe("observation-specific qualification and grouping", () => {
  it("renders three observations rather than five rows for the reported combination", () => {
    const docs = [abstained[0]!, abstained[1]!, completed[2]!];
    const items = groupReviewItems(docs);
    expect(items.map(i => i.area)).toEqual(["Document placement", "Manufacturer metadata", "Applicant information"]);
    expect(items.slice(0, 2).every(i => i.qualifications.includes("inspection_incomplete"))).toBe(true);
    expect(items[0]!.statuses).toContain("Human review required");
    expect(items[1]!.next).toBe("Complete document inspection before deciding reuse.");
    expect(items[2]!.statuses).not.toContain("Incomplete inspection");
    expect(docs[0]!.action).toBe("CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT");
    expect(docs[0]!.explanation?.repair?.description).toContain("suspend the legacy context");
  });
  it("retains inspection-only review and additional independent findings without a row cap", () => {
    expect(documentReviewItems(abstained[2]!)).toHaveLength(1);
    expect(documentReviewItems(abstained[2]!)[0]!.area).toBe("Document inspection");
    const more = { ...completed[2]!, explanation: { ...completed[2]!.explanation!, findings: Array.from({ length: 5 }, (_, i) => ({ ...completed[2]!.explanation!.findings![0]!, id: `independent-${i}` })) } };
    expect(documentReviewItems(more)).toHaveLength(5);
  });
  it("does not assign unrelated semantic badges to placement and keeps system identities distinct", () => {
    const mixed = projectDocument({ ...completed[0]!, explanation: { ...completed[0]!.explanation!, findings: [...completed[0]!.explanation!.findings!, ...completed[2]!.explanation!.findings!] } });
    expect(documentReviewItems(mixed)[0]!.statuses).not.toContain("Supported semantic concern");
    const direct = { ...mixed, system: "B0" as const };
    expect(groupReviewItems([mixed, direct])).toHaveLength(4);
    expect(documentReviewItems(mixed)[0]!.id).not.toBe(documentReviewItems(direct)[0]!.id);
  });
  it("treats B2 omission as a capability boundary, with no request to change B2", () => {
    const cell = (fixture.comparison as ComparisonRun).results.find(c => c.system === "B2" && c.leaf_id === inventory.leaves[2]!.id)!;
    const items = documentReviewItems(comparisonDocument(inventory.leaves[2]!, cell));
    expect(items[0]!.qualifications).toContain("inspection_omitted");
    expect(items[0]!.next).not.toMatch(/complete document inspection/i);
    expect(items[0]!.statuses).not.toContain("Failed analysis");
  });
  it("distinguishes absent cited analysis evidence from unavailable source presentation metadata", () => {
    const d = completed[0]!;
    render(<DocumentReview document={{ ...d, explanation: { ...d.explanation!, evidence: [], sources: [], limitations: ["Pinned source metadata unavailable."] } }}/>);
    fireEvent.click(screen.getByText("View supporting evidence"));
    expect(screen.getByText(/Cited analysis evidence is missing/)).toBeVisible();
    expect(screen.getByText(/Presentation limitation: Pinned source metadata unavailable/)).toBeVisible();
    expect(d.decision).toBe("REUSE_WITH_NEW_CONTEXT");
  });
});

it("keeps saved metadata intent but makes new product setup prospective", () => {
  const context = { ...defaultTarget(), scenario_mode: "current_operational", metadata_plan: { ...defaultTarget().metadata_plan, intent: "preserve-existing-lifecycle" } };
  sessionStorage.setItem("regbridge.target", JSON.stringify({ inventoryId: inventory.id, context }));
  expect(savedTarget(inventory.id).scenario_mode).toBe("prospective_forward_compatibility");
  expect(savedTarget(inventory.id).metadata_plan.intent).toBe("preserve-existing-lifecycle");
  expect((JSON.parse(sessionStorage.getItem("regbridge.target")!) as { context: { scenario_mode: string } }).context.scenario_mode).toBe("current_operational");
});

it("explains intent without changing radio selection and dismisses help", () => {
  function Setup() { const [value, setValue] = useState(defaultTarget); return <ProductSetup value={value} onChange={setValue}/>; }
  render(<Setup/>);
  const undecided = screen.getByRole("radio", { name: "I’m not sure yet" });
  fireEvent.click(screen.getByRole("button", { name: "About preserve existing metadata" }));
  expect(screen.getByRole("note")).toBeVisible();
  expect(undecided).toBeChecked();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("note")).toBeNull();
  fireEvent.click(screen.getByRole("radio", { name: "Preserve existing metadata" }));
  expect(screen.getByText(/Effective intent: Preserve existing metadata/)).toBeVisible();
  expect(screen.queryByRole("combobox")).toBeNull();
});

it("lets upload replace a pending sample and cancellation retain a previous file", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(r => { resolve = r; })));
  function Picker() { const [file, setFile] = useState<File | null>(null); return <DossierPicker file={file} onChange={setFile}/>; }
  render(<Picker/>);
  fireEvent.click(screen.getByRole("button", { name: "Try a sample dossier" }));
  const upload = screen.getByLabelText("Dossier ZIP");
  fireEvent.change(upload, { target: { files: [new File(["zip"], "my-dossier.zip")] } });
  await act(async () => { resolve(new Response(new Blob(["sample"]))); await Promise.resolve(); });
  expect(screen.getByText("Selected: my-dossier.zip")).toBeVisible();
  fireEvent.change(upload, { target: { files: [] } });
  expect(screen.getByText("Selected: my-dossier.zip")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(screen.queryByText(/Selected:/)).toBeNull();
});

it("shows configuration errors without cosmetic model identities or a fallback", () => {
  render(<ConfigurationDisclosure config={{ ...fixture.configuration, availability: "misconfigured" } as Parameters<typeof ConfigurationDisclosure>[0]["config"]}/>);
  expect(within(screen.getByRole("alert")).getByText(/Contact the service operator/)).toBeVisible();
  expect(screen.queryByText(/gpt-5.5|Offline demonstration/)).toBeNull();
});
