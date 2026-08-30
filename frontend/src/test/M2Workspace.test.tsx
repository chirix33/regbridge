import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";

afterEach(() => {
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("M2 shared analysis workspace", () => {
  it("sends explicit normalization intent and distinguishes advisory from hard findings", async () => {
    window.history.pushState({}, "", "/case-b");
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    let analysisBody: Record<string, unknown> | null = null;
    const fixture = {
      id: "case-b-normalize-all",
      title: "Normalize discouraged manufacturer metadata",
      description: "Canonical Case B.",
      expected_class: "positive",
      archetype: "legacy-metadata-tension",
      default_metadata_intent: "normalize-metadata",
      manufacturer_partitioning: "unnecessary",
      replacement_manufacturer_value: null,
      author_verified_relevant_hyperlink_ids: [],
    };
    const leaf = {
      id: "leaf-b-normalize-all",
      title: "Manufacturer overview",
      heading: "3.2.S.1",
      href: "documents/case-b.pdf",
      operation: "new",
      content_type: "application/pdf",
      file_sha256: "b".repeat(64),
      source_locator: "index.xml / 3.2.S.1 / leaf[leaf-b-normalize-all]",
      keywords: [{ name: "manufacturer", raw_value: "all", normalized_value: "all", source_locator: "index.xml / 3.2.S.1 / @manufacturer" }],
      text_span_count: 1,
      hyperlink_count: 0,
      extraction_status: "completed",
    };
    const inventory = { id: "inventory-b", fixture_id: fixture.id, source_standard: "eCTD-3.2.2", application_number: "123456", submission_type: "original", applicant_name: "Northstar", has_stf: false, package_sha256: "a".repeat(64), leaves: [leaf], warnings: [] };
    const analysis = {
      id: "analysis-b",
      source_artifact: { id: "artifact-b", title: leaf.title, source_leaf_id: leaf.id, source_heading: leaf.heading, source_locator: leaf.source_locator, file_sha256: leaf.file_sha256 },
      target_context: { scenario_mode: "prospective_forward_compatibility", metadata_plan: { intent: "normalize-metadata", manufacturer_partitioning: "unnecessary", replacement_manufacturer_value: null } },
      operational_status: "not_operational",
      scenario_disclosure: "Controlled prospective scenario.",
      expert_validated: false,
      decision: "REUSE_WITH_NEW_CONTEXT",
      severity: "blocking",
      triggered_rule_ids: ["advisory", "hard"],
      findings: [
        { id: "advisory", rule_id: "advisory", severity: "medium", rationale: "The general value is not recommended when unnecessary.", evidence_ids: ["ev-m4"], source: "deterministic", verification_basis: "direct_standard_encoding", enforcement_mode: "advisory" },
        { id: "hard", rule_id: "hard", severity: "blocking", rationale: "Explicit normalization requires a new context group.", evidence_ids: ["ev-m4"], source: "deterministic", verification_basis: "mechanical_derivation", enforcement_mode: "hard" },
      ],
      evidence: [{ id: "ev-m4", source_id: "fda-m4", locator: "Appendix A / PDF page 25", text: "General manufacturer values are not recommended.", bindingness: "recommendation", source_sha256: "c".repeat(64), review_status: "source_verified", verification_basis: "direct_standard_encoding", enforcement_mode: "disabled", expert_validated: false }],
      rationale: "Explicit normalization changes the context group.",
      repair: { type: "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD", description: "Omit the keyword and reuse the unchanged document by identifier.", evidence_ids: ["ev-m4"] },
      confidence: 1,
      unresolved_uncertainty: [],
      human_approval_required: true,
      trace: [{ sequence: 1, kind: "synthesis", component: "decision-synthesizer", summary: "Applied precedence.", evidence_ids: [] }],
      model_run: { mode: "fixture", status: "completed", prompt_template_version: "1.0.0", model_name: "fixture", input_tokens: null, output_tokens: null, latency_ms: 0, validation_error: null },
    };
    const graph = { analysis_id: analysis.id, nodes: [{ id: "artifact-b", type: "artifact", label: leaf.title, version: null, review_status: null }], edges: [], text_alternative: ["artifact has controlled findings."] };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/api/v1/fixtures")) return Promise.resolve(new Response(JSON.stringify({ fixtures: [fixture] }), { status: 200 }));
      if (url.includes("applications/parse")) return Promise.resolve(new Response(JSON.stringify(inventory), { status: 200 }));
      if (url.includes("/graph")) return Promise.resolve(new Response(JSON.stringify({ graph }), { status: 200 }));
      if (typeof init?.body === "string") analysisBody = JSON.parse(init.body) as Record<string, unknown>;
      return Promise.resolve(new Response(JSON.stringify({ analysis }), { status: 200 }));
    }));

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Parse and analyze/i }));
    expect(await screen.findByText("REUSE WITH NEW CONTEXT")).toBeVisible();
    expect(screen.getByText(/deterministic · advisory/i)).toBeVisible();
    expect(screen.getByText(/deterministic · hard/i)).toBeVisible();
    const context = (analysisBody as { target_context?: { metadata_plan?: unknown } } | null)?.target_context;
    expect(context?.metadata_plan).toEqual({ intent: "normalize-metadata", manufacturer_partitioning: "unnecessary", replacement_manufacturer_value: null });
  });
});
