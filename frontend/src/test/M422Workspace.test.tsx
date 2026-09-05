import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "../App";

const sha = "a".repeat(64);
const models = {
  default_model_id: "gpt-5.5",
  models: [
    {
      model_id: "gpt-5.5",
      display_name: "Deterministic fixture — GPT-5.5 contract",
      subtitle: null,
      availability: "available",
      disabled_reason: null,
      adapter_type: "responses",
      execution_mode: "fixture",
      actual_adapter_type: "fixture",
      configured_model_name: "internal-package-derived-fixture",
      structured_output_capability: "validated",
      reasoning_capability: true,
      configuration_digest: sha,
      network_required: false,
    },
  ],
};

const inventory = {
  id: "inv-" + "a".repeat(32),
  fixture_id: null,
  source_standard: "eCTD-3.2.2",
  application_number: "999999",
  submission_type: "original",
  applicant_name: "Synthetic Applicant",
  has_stf: false,
  package_sha256: sha,
  leaves: [
    { id: "leaf-a", title: "Synthetic molecular structure", policy_coverage_status: "EVALUATED_WITH_APPROVED_POLICY", policy_coverage_basis: "Exact policy", heading: "3.2.S.1.2" },
    { id: "leaf-b", title: "Synthetic lifecycle metadata context", policy_coverage_status: "EVALUATED_WITH_APPROVED_POLICY", policy_coverage_basis: "Exact policy", heading: "3.2.S.1" },
    { id: "leaf-c", title: "Terminally failed document", policy_coverage_status: "EVALUATED_WITH_APPROVED_POLICY", policy_coverage_basis: "Exact policy", heading: "3.2.S.1" },
  ],
  warnings: [],
  input_profile_id: "fda-cder-ectd-322-public-standards-profile-v1",
  input_profile_version: "1.0.0",
  detected_sequence_root: "synthetic-application/0000",
  package_profile_status: "passed",
  index_md5_matches: true,
  policy_coverage_counts: { EVALUATED_WITH_APPROVED_POLICY: 3 },
  xml_declarations: [],
  profile_checks: [],
  package_files: [],
};

function result(
  leafId: string,
  title: string,
  status: "completed" | "abstained",
  decision: string,
  basis: string,
) {
  const limitation = status === "abstained" ? [{
    id: "limitation-semantic-inspection",
    type: "analysis_limitation",
    label: "Semantic inspection abstained",
    version: null,
    review_status: null,
    properties: { component: "semantic-inspection", status: "abstained" },
  }] : [];
  return {
    leaf_id: leafId,
    analysis_ref: `analysis-${leafId}`,
    analysis: {
      source_artifact: { title },
      decision,
      severity: decision === "REUSE_WITH_NEW_CONTEXT" ? "blocking" : "unresolved",
      human_approval_required: true,
      rationale: status === "abstained" ? "Inspection is incomplete; no stale finding was made." : "Hard structural mapping applies.",
      repair: { type: status === "abstained" ? "COMPLETE_DOCUMENT_INSPECTION" : "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT", description: "Bounded next action." },
      findings: [],
      trace: [{ sequence: 1, component: "semantic-inspection", summary: `Semantic inspection ${status}.` }],
      decision_basis: basis,
    },
    graph: {
      analysis_id: `analysis-${leafId}`,
      nodes: [{ id: `artifact-${leafId}`, type: "artifact", label: title, version: null, review_status: null, properties: {} }, ...limitation, { id: `decision-${leafId}`, type: "decision", label: decision, version: null, review_status: null, properties: {} }],
      edges: limitation.length ? [{ id: "edge-limit", source: "limitation-semantic-inspection", target: `decision-${leafId}`, type: "LEAVES_UNRESOLVED", label: "leaves unresolved", evidence_ids: [], review_status: null }] : [],
      text_alternative: [status === "abstained" ? "Semantic inspection abstention leaves the decision unresolved." : "The active hard rule determines the decision."],
    },
    model: {
      model_profile_id: "gpt-5.5",
      requested_model_name: "internal-package-derived-fixture",
      provider_reported_model_name: "internal-package-derived-fixture",
      adapter_type: "fixture",
      execution_mode: "fixture",
      configuration_digest: sha,
      prompt_version: "1.0.0",
      request_digest: sha,
      input_tokens: 10,
      output_tokens: 5,
      reasoning_tokens: null,
      latency_ms: 0,
      attempt_count: 1,
      retry_causes: [],
      status,
      reason_category: status === "abstained" ? "insufficient_bounded_evidence" : null,
      status_detail: status === "abstained" ? "The model abstained because bounded evidence was insufficient." : null,
      failure: null,
    },
  };
}

const run = {
  run_id: "dossier-" + "b".repeat(64),
  state: "partial_failed",
  inventory_id: inventory.id,
  input_profile_id: inventory.input_profile_id,
  selected_model: models.models[0],
  execution_configuration_digest: sha,
  requested_leaf_ids: ["leaf-a", "leaf-b", "leaf-c"],
  summary: {
    package_sha256: sha,
    application_number: "999999",
    submission_type: "original",
    applicant_name: "Synthetic Applicant",
    total_supported_leaves: 3,
    analyzed_count: 2,
    failed_count: 1,
    pipeline_failure_count: 1,
    model_abstention_count: 1,
    skipped_count: 0,
    decision_counts: { REUSE_WITH_NEW_CONTEXT: 1, HUMAN_REGULATORY_REVIEW: 1 },
    severity_counts: { blocking: 1, unresolved: 1 },
    human_approval_count: 2,
    parser_warning_count: 0,
    policy_coverage_counts: { EVALUATED_WITH_APPROVED_POLICY: 3 },
  },
  results: [
    result("leaf-a", "Synthetic molecular structure", "completed", "REUSE_WITH_NEW_CONTEXT", "deterministic_hard_rule"),
    result("leaf-b", "Synthetic lifecycle metadata context", "abstained", "HUMAN_REGULATORY_REVIEW", "abstention_gate"),
  ],
  failures: [{ leaf_id: "leaf-c", stage: "semantic_processing", cause: "AnalysisPipelineError", failure_category: "invalid_structured_output", retryable: false }],
  operational_status: "not_operational",
  expert_validated: false,
  capability_boundary: "Bounded research prototype.",
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

it("shows abstention as completed analysis and separates pipeline failures", async () => {
  window.history.pushState({}, "", "/");
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.endsWith("/api/v1/models")) return Promise.resolve(new Response(JSON.stringify(models), { status: 200 }));
    if (url.includes("/api/v1/applications/parse")) return Promise.resolve(new Response(JSON.stringify(inventory), { status: 200 }));
    return Promise.resolve(new Response(JSON.stringify(run), { status: 200 }));
  }));
  render(<App />);

  expect(
    await screen.findByText(
      (_content, element) =>
        element?.tagName === "P" &&
        element.textContent?.includes(
          "Execution: fixture · actual adapter fixture · network-free",
        ) === true,
    ),
  ).toBeVisible();
  fireEvent.change(screen.getByLabelText("Dossier ZIP"), { target: { files: [new File(["zip"], "synthetic.zip", { type: "application/zip" })] } });
  fireEvent.click(screen.getByLabelText(/I confirm this target context/i));
  fireEvent.click(screen.getByRole("button", { name: "Parse and analyze" }));

  const abstentions = await screen.findByText("Model abstentions");
  expect(abstentions.closest("article")).toHaveTextContent("1Model abstentions");
  const failures = screen.getByText("Pipeline failures");
  expect(failures.closest("article")).toHaveTextContent("1Pipeline failures");
  const analyzed = screen.getByText("Successfully analyzed");
  expect(analyzed.closest("article")).toHaveTextContent("2Successfully analyzed");

  const resultTitle = screen
    .getAllByText("Synthetic lifecycle metadata context")
    .find((element) => element.closest("details") !== null);
  expect(resultTitle).toBeDefined();
  fireEvent.click(resultTitle as HTMLElement);
  const details = (resultTitle as HTMLElement).closest("details");
  expect(details).not.toBeNull();
  expect(within(details as HTMLElement).getByText("abstained")).toBeVisible();
  expect(within(details as HTMLElement).queryByText("failed")).not.toBeInTheDocument();
  expect(within(details as HTMLElement).getByText(/Analysis completed with deterministic synthesis/)).toBeVisible();
  expect(within(details as HTMLElement).getByText("analysis limitation")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Pipeline failure" })).toBeVisible();
  expect(screen.getByText(/No regulatory decision was published/)).toBeVisible();
});
