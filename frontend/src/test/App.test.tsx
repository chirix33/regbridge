import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";

const scopeResponse = {
  product_name: "RegBridge",
  product_type: "research prototype",
  research_question: "Can typed evidence improve reuse decisions?",
  authority: "FDA",
  center: "CDER",
  supported_application_types: ["NDA"],
  source_standards: ["eCTD-3.2.2"],
  target_standards: ["eCTD-4.0"],
  standards_snapshot_id: "fda-cder-demo-v1",
  model_mode: "fixture",
  network_required: false,
  operational_status: "not_operational",
  approved_research_scenario: "prospective_forward_compatibility",
  expert_validated: false,
  available_features: ["scope"],
  planned_archetypes: [
    "unavailable-heading",
    "legacy-metadata-tension",
    "stale-content-or-hyperlink",
  ],
  disclaimer: "Research prototype. Not FDA-certified and not regulatory advice.",
  limitations: ["FDA/CDER only."],
};

const standardsResponse = {
  snapshot_id: "fda-cder-demo-v1",
  manifest_version: "1.0.0",
  description: "Reviewed M0 source registry.",
  sources: [
    {
      id: "fda-ectd-v4-tcg-v1.5",
      title: "Electronic Common Technical Document v4.0 Technical Conformance Guide",
      version: "1.5 (June 2026)",
      authority: "FDA",
      center: "CDER",
      source_url: "https://www.fda.gov/example",
      sha256: "d".repeat(64),
      review_status: "source_verified",
      verification_basis: "direct_standard_encoding",
      enforcement_mode: "disabled",
      expert_validated: false,
      reviewer_note: "Registry inclusion review only.",
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("RegBridge scope", () => {
  it("shows the disclaimer, operational status, scope, and source-verified registry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const payload = url.includes("/standards/") ? standardsResponse : scopeResponse;
        return Promise.resolve(
          new Response(JSON.stringify(payload), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );

    render(<App />);

    expect(await screen.findByText("Offline fixture mode")).toBeVisible();
    expect(screen.getByLabelText("Research prototype disclaimer")).toHaveTextContent(
      "Not FDA-certified",
    );
    expect(screen.getByText("eCTD-3.2.2")).toBeVisible();
    expect(screen.getByText("eCTD-4.0")).toBeVisible();
    expect(screen.getByText("Source-verified registry")).toBeVisible();
    expect(screen.getByText(/FDA forward compatibility: not_operational/i)).toBeVisible();
    expect(screen.getByText(/expert validated: no/i)).toBeVisible();
    expect(screen.getByRole("link", { name: /Open official FDA source/i })).toHaveAttribute(
      "href",
      "https://www.fda.gov/example",
    );
  });
});
