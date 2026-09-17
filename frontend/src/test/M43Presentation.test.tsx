import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import fixture from "./fixtures/m43-product.json";
import type { ApplicationInventory, ComparisonRun, DossierAnalysisRun } from "../api/contracts";
import { comparisonDocument, dossierDocuments, groupReviewItems, projectDocument } from "../api/presentation";
import { DocumentReview, ReviewWorkspace } from "../components/ReviewWorkspace";
import { defaultTarget, savedTarget } from "../api/targetSetup";

const inventory = fixture.inventory as ApplicationInventory;
const run = fixture.run as DossierAnalysisRun;
const comparison = fixture.comparison as ComparisonRun;
const documents = dossierDocuments(inventory, run);
const structural = documents.find(d => d.decision === "REUSE_WITH_NEW_CONTEXT")!;
const semantic = documents.find(d => d.statuses.includes("Supported semantic concern"))!;

describe("versioned product presentation", () => {
  it("projects new context and supported concerns from actual recorded data", () => {
    expect(structural.statuses).toContain("Required context/metadata action");
    expect(semantic.statuses).toContain("Supported semantic concern");
    expect(semantic.explanation?.evidence.length).toBeGreaterThan(0);
  });
  it("keeps the hard recommendation and approval with incomplete inspection", () => {
    const d = projectDocument({ ...structural, model: { ...structural.model!, status: "abstained" } });
    expect(d.statuses).toContain("Incomplete inspection");
    expect(d.action).toBe("CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT");
    expect(d.approval).toBe(true);
    expect(d.statuses).not.toContain("Supported semantic concern");
  });
  it("does not fabricate findings for abstention", () => {
    const d = projectDocument({ ...semantic, action: "COMPLETE_DOCUMENT_INSPECTION", model: { ...semantic.model!, status: "abstained" }, explanation: { ...semantic.explanation!, findings: [] } });
    expect(d.statuses).toContain("Incomplete inspection");
    expect(d.statuses).not.toContain("Supported semantic concern");
  });
  it("qualifies a clean eligible result and retains absent history and outside coverage", () => {
    const clean = { ...semantic, decision: "REUSE_AS_LEGACY_REFERENCE", action: "NO_MATERIAL_REPAIR", approval: false, explanation: { ...semantic.explanation!, findings: [], uncertainty: [] } };
    expect(projectDocument(clean).statuses).toEqual(["No change detected within evaluated checks"]);
    expect(projectDocument(clean).attention).toBe(false);
    for (const coverage of ["INSUFFICIENT_APPLICATION_HISTORY", "OUTSIDE_ENCODED_POLICY_COVERAGE", "DOCUMENT_INSPECTION_INCOMPLETE"] as const) {
      const d = projectDocument({ ...clean, leaf: { ...clean.leaf, policy_coverage_status: coverage } });
      expect(d.attention).toBe(true);
      expect(d.statuses).not.toContain("No change detected within evaluated checks");
    }
  });
  it("distinguishes service failure, not analyzed, and B2 omission", () => {
    expect(projectDocument({ ...structural, decision: null, action: null }, true).statuses).toContain("Failed analysis");
    expect(projectDocument({ ...structural, decision: null, action: null }).statuses).toContain("Not analyzed");
    const b2 = comparison.results.find(c => c.system === "B2")!;
    expect(comparisonDocument(inventory.leaves.find(l => l.id === b2.leaf_id)!, b2).statuses).toContain("Inspection intentionally omitted");
  });
  it("retains multiple findings and groups only equivalent document conditions", () => {
    const multi = { ...semantic, explanation: { ...semantic.explanation!, observations: { ...semantic.explanation!.observations!, semantic_topics: [...semantic.explanation!.observations!.semantic_topics, { finding_id: "second-finding", category: "applicant_name_mismatch" }] }, findings: [...semantic.explanation!.findings!, { ...semantic.explanation!.findings![0]!, id: "second-finding" }] } };
    const another = { ...multi, leaf: { ...multi.leaf, id: "second-doc", href: "m3/another.pdf" } };
    const groups = groupReviewItems([multi, another]);
    expect(groups).toHaveLength(2);
    expect(groups[0]!.documents).toHaveLength(2);
    expect(groups[0]!.documents[0]!.explanation!.findings).toHaveLength(2);
    const qualified = { ...another, explanation: { ...another.explanation, uncertainty: ["A distinct unresolved condition"] } };
    expect(groupReviewItems([multi, qualified])).toHaveLength(4);
  });
  it("retains unfamiliar recorded recommendations with a presentation limitation", () => {
    const d = projectDocument({ ...structural, action: "NEW_UNRECOGNIZED_ACTION" });
    expect(d.limitation).toBeTruthy();
    expect(d.decision).toBe(structural.decision);
  });
  it("opens document identity and action before independent evidence and technical disclosures", () => {
    render(<ReviewWorkspace documents={[structural]}/>);
    expect(screen.getByRole("button", { name: "Needs attention" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Document placement" }));
    expect(screen.getByText(structural.leaf.href)).toBeVisible();
    expect(screen.getAllByText("Next step")[0]).toBeVisible();
    expect(screen.getByText("View supporting evidence").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("How RegBridge reached this result").closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("View supporting evidence"));
    expect(screen.getAllByRole("link", { name: "Official source" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Close document review" }));
    expect(screen.getByRole("button", { name: "Document placement" })).toHaveFocus();
  });
  it("does not attach RegBridge explanation to direct approaches", () => {
    const b0 = comparison.results.find(c => c.system === "B0")!;
    expect(b0.explanation!.findings).toBeNull();
    expect(b0.graph).toBeNull();
    expect(b0.explanation!.observations!.placements).toEqual([]);
    expect(b0.explanation!.observations!.semantic_topics).toEqual([]);
    expect(b0.explanation!.observations!.keywords).toEqual([]);
    expect(b0.explanation!.evidence.map(e => e.id).sort()).toEqual([...b0.evidence_ids].sort());
    render(<DocumentReview document={comparisonDocument(inventory.leaves.find(l => l.id === b0.leaf_id)!, b0)}/>);
    expect(screen.getByText(b0.rationale!)).toBeVisible();
  });
  it("preserves matching target context and never substitutes preservation for absent context", () => {
    sessionStorage.clear();
    expect(savedTarget(inventory.id).metadata_plan.intent).toBe("unspecified");
    const context = { ...defaultTarget(), metadata_plan: { ...defaultTarget().metadata_plan, intent: "normalize-metadata" as const } };
    sessionStorage.setItem("regbridge.target", JSON.stringify({ inventoryId: inventory.id, context }));
    expect(savedTarget(inventory.id)).toEqual(context);
    expect(savedTarget("other").metadata_plan.intent).toBe("unspecified");
  });
});
