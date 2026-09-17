import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import fixture from "./fixtures/m43-product.json";
import type { ApplicationInventory, DossierAnalysisRun } from "../api/contracts";
import { documentReviewItems, dossierDocuments, projectDocument } from "../api/presentation";
import { ReviewWorkspace } from "../components/ReviewWorkspace";

const inventory = fixture.inventory as ApplicationInventory;
const docs = dossierDocuments(inventory, fixture.run as DossierAnalysisRun);
const placement = docs.find(d => d.explanation?.observations?.placements.length)!;
const manufacturer = docs.find(d => d.leaf.keywords.some(k => k.name === "manufacturer" && k.raw_value === "all"))!;
const applicant = docs.find(d => d.explanation?.observations?.semantic_topics.length)!;
const rows = (d: typeof manufacturer) => documentReviewItems(d);
const metadata = (d: typeof manufacturer) => rows(d).find(i => i.area === "Manufacturer metadata")!;

describe("concrete review observations and leaf inventory", () => {
  it("shows the actual manufacturer property/value without stale sample wording", () => {
    expect(metadata(manufacturer).found).toContain('manufacturer="all"');
    const changed = { ...manufacturer, leaf: { ...manufacturer.leaf, keywords: manufacturer.leaf.keywords.map(k => k.name === "manufacturer" ? { ...k, raw_value: "Example Manufacturing" } : k) } };
    expect(metadata(changed).found).toContain('manufacturer="Example Manufacturing"');
    expect(metadata(changed).found).not.toContain('manufacturer="all"');
  });
  it("acknowledges preservation and retains its eligibility and advisory", () => {
    expect(metadata(manufacturer).found).toContain("Existing lifecycle preservation was selected");
    expect(metadata(manufacturer).found).toContain("Recorded advisory");
    expect(metadata(manufacturer).next).not.toMatch(/confirm|choose/i);
    expect(manufacturer.decision).toBe("REUSE_AS_LEGACY_REFERENCE");
  });
  it("separates unconfirmed intent from incomplete inspection", () => {
    const missing = projectDocument({ ...manufacturer, action: "DECLARE_METADATA_MIGRATION_INTENT", explanation: { ...manufacturer.explanation!, observations: { ...manufacturer.explanation!.observations!, metadata_plan: { ...manufacturer.explanation!.observations!.metadata_plan!, intent: "unspecified" } } } });
    expect(metadata(missing).found).toContain("Migration intent is not yet confirmed");
    expect(metadata(missing).next).toContain("Confirm the intended metadata migration");
    expect(rows(missing).some(i => i.area === "Document inspection")).toBe(false);
    expect(missing.statuses).not.toContain("Incomplete inspection");
  });
  it("retains inspection action and selected intent on abstention without stale-content claims", () => {
    const abstained = dossierDocuments(inventory, fixture.abstention as DossierAnalysisRun).find(d => d.leaf.id === manufacturer.leaf.id)!;
    expect(metadata(abstained).found).toContain('manufacturer="all"');
    expect(metadata(abstained).found).toContain("preservation was selected");
    expect(metadata(abstained).found).toContain("inspection remains incomplete");
    expect(metadata(abstained).next).toBe("Complete document inspection before deciding reuse.");
    expect(abstained.action).toBe("COMPLETE_DOCUMENT_INSPECTION");
    expect(abstained.explanation?.findings?.some(f => f.verification_basis === "semantic_inference")).toBe(false);
  });
  it("retains normalization and partition uncertainty", () => {
    const normalized = projectDocument({ ...manufacturer, action: "DECLARE_MANUFACTURER_PARTITIONING", explanation: { ...manufacturer.explanation!, observations: { ...manufacturer.explanation!.observations!, metadata_plan: { ...manufacturer.explanation!.observations!.metadata_plan!, intent: "normalize-metadata", manufacturer_partitioning: "unknown" } } } });
    expect(metadata(normalized).found).toContain("normalization was selected");
    expect(metadata(normalized).found).toContain("partitioning remains unresolved");
    expect(metadata(normalized).next).toContain("partitioning");
  });
  it("exposes supported heading facts and source-labeled applicant evidence", () => {
    const p = rows(placement)[0]!;
    expect(p.area).toBe("Document placement");
    expect(p.found).toContain(placement.leaf.heading);
    expect(p.next).toContain(placement.explanation!.observations!.placements[0]!.target_heading);
    const a = rows(applicant).find(i => i.area === "Applicant information")!;
    const evidence = applicant.explanation!.evidence.find(e => applicant.explanation!.findings![0]!.evidence_ids.includes(e.id))!;
    expect(a.found).toContain(`Document text: “${evidence.text}”`);
    expect(a.found).toContain(`Package metadata applicant: “${inventory.applicant_name}”`);
  });
  it("uses one inventory row per leaf including clean, failed and shared-file contexts", () => {
    const clean = projectDocument({ ...applicant, leaf: { ...applicant.leaf, id: "clean", title: "Clean result" }, decision: "REUSE_AS_LEGACY_REFERENCE", action: "NO_MATERIAL_REPAIR", approval: false, explanation: { ...applicant.explanation!, findings: [], uncertainty: [] } });
    const failed = projectDocument({ ...applicant, leaf: { ...applicant.leaf, id: "failed", title: "Failed result" }, decision: null, action: null }, true);
    render(<ReviewWorkspace documents={[applicant, clean, failed]}/>);
    fireEvent.click(screen.getByRole("button", { name: "All documents" }));
    const table = screen.getByRole("table", { name: "Document inventory" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByRole("button", { name: "Clean result" })).toBeVisible();
    expect(within(table).getByText("Failed analysis")).toBeVisible();
    expect(within(table).getByText("0 review items")).toBeVisible();
    expect(within(table).getAllByText(applicant.leaf.href)).toHaveLength(3);
  });
  it("keeps distinct views when every leaf needs attention and opens every document item", () => {
    const multi = projectDocument({ ...placement, explanation: { ...placement.explanation!, findings: [...placement.explanation!.findings!, ...applicant.explanation!.findings!], evidence: [...placement.explanation!.evidence, ...applicant.explanation!.evidence], observations: { ...placement.explanation!.observations!, semantic_topics: applicant.explanation!.observations!.semantic_topics } } });
    render(<ReviewWorkspace documents={[multi]}/>);
    expect(screen.getByRole("table", { name: "Action overview" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Applicant information" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "All documents" }));
    expect(screen.queryByRole("table", { name: "Action overview" })).toBeNull();
    const table = screen.getByRole("table", { name: "Document inventory" });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).getByText("2 review items")).toBeVisible();
    fireEvent.click(within(table).getByRole("button", { name: multi.leaf.title }));
    const detail = screen.getByRole("region", { name: /^Review items for/ });
    expect(within(detail).getByText("Document placement")).toBeVisible();
    expect(within(detail).getByText("Applicant information")).toBeVisible();
    expect(screen.getByText(multi.explanation!.repair!.description, { selector: "dd" })).toBeVisible();
  });
  it("keeps full lifecycle instructions, incomplete inspection and approval in expanded detail", () => {
    const d = dossierDocuments(inventory, fixture.abstention as DossierAnalysisRun).find(d => d.leaf.id === placement.leaf.id)!;
    render(<ReviewWorkspace documents={[d]}/>);
    const overview = screen.getByRole("table", { name: "Action overview" });
    expect(within(overview).queryByText(d.explanation!.repair!.description)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Document placement" }));
    expect(screen.getByText(d.explanation!.repair!.description, { selector: "dd" })).toBeVisible();
    expect(screen.getByText(/Required before acting on the recommendation/)).toBeVisible();
    expect(screen.getByText("Inspection incomplete.")).toBeVisible();
    expect(screen.getByText(d.leaf.href)).toBeVisible();
  });
});
