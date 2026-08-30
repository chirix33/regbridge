import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";

const fixtures = {
  fixtures: [
    {
      id: "case-a-removed-3211",
      title: "Removed heading 3.2.S.1.1",
      description: "Positive controlled case.",
      expected_class: "positive",
    },
  ],
};

const inventory = {
  id: "inventory-case-a-removed-3211",
  fixture_id: "case-a-removed-3211",
  source_standard: "eCTD-3.2.2",
  application_number: "999001",
  submission_type: "original",
  applicant_name: "Synthetic Research Sponsor",
  has_stf: false,
  package_sha256: "a".repeat(64),
  leaves: [
    {
      id: "leaf-3211",
      title: "Substance name and structure",
      heading: "3.2.S.1.1",
      href: "documents/substance-name.pdf",
      operation: "new",
      content_type: "application/pdf",
      file_sha256: "b".repeat(64),
      source_locator: "index.xml / 3.2.S.1.1 / leaf[leaf-3211]",
    },
  ],
  warnings: [],
};

const evidence = {
  id: "ev-ctoc-3211-3213-removed",
  source_id: "fda-ectd-v4-ctoc-v2.2",
  locator: "PDF page 39 / printed page 36",
  text: "The three subheadings are removed.",
  bindingness: "informative",
  source_sha256: "c".repeat(64),
  review_status: "source_verified",
  verification_basis: "direct_standard_encoding",
  enforcement_mode: "disabled",
  expert_validated: false,
};

const result = {
  analysis: {
    id: "analysis-1",
    source_artifact: {
      id: "artifact-leaf-3211",
      title: "Substance name and structure",
      source_leaf_id: "leaf-3211",
      source_heading: "3.2.S.1.1",
      source_locator: "index.xml / 3.2.S.1.1 / leaf[leaf-3211]",
      file_sha256: "b".repeat(64),
    },
    target_context: { scenario_mode: "prospective_forward_compatibility" },
    operational_status: "not_operational",
    scenario_disclosure: "Prospective research scenario.",
    expert_validated: false,
    decision: "REUSE_WITH_NEW_CONTEXT",
    severity: "blocking",
    triggered_rule_ids: ["FDA-CDER-M1-REMOVED-SUBHEADING-001"],
    evidence: [evidence],
    rationale: "The document can be reused by identifier in a new context.",
    repair: {
      type: "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT",
      description: "Create a new context; do not resubmit the physical file.",
      evidence_ids: [evidence.id],
    },
    confidence: 1,
    unresolved_uncertainty: [],
    human_approval_required: true,
    trace: [
      {
        sequence: 1,
        kind: "deterministic",
        component: "explicit-heading-rule-engine",
        summary: "Matched the exact mapping.",
        evidence_ids: [evidence.id],
      },
    ],
  },
};

const graph = {
  graph: {
    analysis_id: "analysis-1",
    nodes: [
      { id: "artifact", type: "artifact", label: "Substance name", version: null, review_status: null },
      { id: "heading", type: "heading", label: "3.2.S.1.1", version: "3.2.2", review_status: "source_verified" },
    ],
    edges: [
      { id: "edge", source: "artifact", target: "heading", type: "LOCATED_UNDER", label: "parsed beneath", evidence_ids: [], review_status: null },
    ],
    text_alternative: ["artifact parsed beneath heading."],
  },
};

afterEach(() => {
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("M1 heading case", () => {
  it("shows parsed placement, decision, repair, evidence, graph, and operational disclosure", async () => {
    window.history.pushState({}, "", "/case-a");
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const payload = url.endsWith("/api/v1/fixtures")
          ? fixtures
          : url.includes("applications/parse")
            ? inventory
            : url.includes("/graph")
              ? graph
              : result;
        return Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }));
      }),
    );

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Parse and analyze/i }));

    expect(await screen.findByText("REUSE WITH NEW CONTEXT")).toBeVisible();
    expect(screen.getAllByText("3.2.S.1.1").length).toBeGreaterThan(0);
    expect(screen.getByText(/CREATE NEW CONTEXT GROUP AND SUSPEND LEGACY CONTENT/i)).toBeVisible();
    expect(screen.getByText("PDF page 39 / printed page 36")).toBeVisible();
    expect(screen.getByText("Why this conclusion is connected")).toBeVisible();
    expect(screen.getAllByText("not_operational").length).toBeGreaterThan(0);
    expect(screen.getAllByText("no").length).toBeGreaterThan(0);
  });
});
