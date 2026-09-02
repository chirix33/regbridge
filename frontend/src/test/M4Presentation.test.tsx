import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";

const metric = {
  system: "B0",
  repetition_index: 1,
  result_status: "live model output",
  accuracy: 0.5,
  macro_f1: 0.5,
  unsafe_false_negative_rate: { numerator: 0, denominator: 8, rate: 0 },
  review_bypass_rate: { numerator: 1, denominator: 4, rate: 0.25 },
  outside_represented_rate: 0.25,
  invalid_outputs: 0,
  invalid_output_rate: 0,
  requests: 12,
  input_tokens: 100,
  output_tokens: 50,
  latency_ms_total: 1200,
  cost_usd: 0.12,
  retrieval: null,
  family_sensitivity: [{ fixture_family: "c-applicant-mismatch", unsafe_misses: 0, eligible_cases: 2 }],
};

const snapshot = {
  schema_version: "m4.presentation.v1",
  snapshot_version: "m4-phase2-20260901T170811002109Z-v1",
  snapshot_sha256: "a".repeat(64),
  source_run_id: "m3-live-phase2-20260901T170811002109Z",
  source_run_directory: "results/live/m3-live-phase2-20260901T170811002109Z",
  source_run_file_sha256: { "manifest.json": "b".repeat(64) },
  predictions_sha256: "7".repeat(64),
  metrics_sha256: "8".repeat(64),
  repository_commit: "abc123",
  benchmark_sha256: "c".repeat(64),
  frozen_prompt_digest: "d".repeat(64),
  frozen_configuration_digest: "e".repeat(64),
  run_type: "live_model_run",
  empirical_model_run: true,
  eligible_for_performance_claims: true,
  current_fda_operational_availability: "not_operational",
  expert_validated: false,
  headline_scope: "held-out-test",
  disclosure:
    "Presentation snapshot derived from frozen Phase 2 run m3-live-phase2-20260901T170811002109Z; results are displayed, not recomputed.",
  limitations: ["expert_validated: false"],
  completion_audit: {
    state: "completed",
    stop_reason: "completed_without_failure",
    scheduled_outcomes: 108,
    completed_outcomes: 108,
  },
  metric_reports: [
    metric,
    { ...metric, system: "B1", repetition_index: 1, retrieval: { result_status: "genuine deterministic retrieval measurement", evaluated_cases: 7, recall_at_3: 0.7, precision_at_3: 0.48, mrr: 1 } },
    { ...metric, system: "B2", repetition_index: null, result_status: "genuine deterministic experimental output", requests: 0, cost_usd: null },
    { ...metric, system: "RegBridge", repetition_index: 1, accuracy: 0.917, review_bypass_rate: { numerator: 0, denominator: 4, rate: 0 } },
  ],
  metric_ranges: {},
  retrieval_summary: {
    result_status: "genuine deterministic retrieval measurement",
    per_repetition: [{ repetition_index: 1, recall_at_3: 0.7, precision_at_3: 0.48, mrr: 1, evaluated_cases: 7 }],
  },
  usage_summary: {},
  cost_summary: { total_cost_usd: 2.744, unknown_cost_outcomes: 0 },
  cases: [
    {
      case_id: "C002",
      fixture_id: "case-c-stale-applicant",
      fixture_family: "c-applicant-mismatch",
      archetype: "stale-content-or-hyperlink",
      split: "test",
      selected_leaf_id: "leaf-c-stale-applicant",
      reference_decision: "HUMAN_REGULATORY_REVIEW",
      reference_action: "HUMAN_VERIFY_STALE_CONTENT",
      reference_severity: "unresolved",
      reference_human_review_required: true,
      mutation: { type: "semantic-text" },
      package_sha256: "f".repeat(64),
      selected_file_sha256: "1".repeat(64),
      decision_fingerprint_sha256: "2".repeat(64),
      varied_predictions: true,
      predictions: [
        {
          system: "B0",
          repetition_index: 1,
          result_status: "live model output",
          outcome: "valid_prediction",
          decision: "HUMAN_REGULATORY_REVIEW",
          action: "HUMAN_VERIFY_STALE_CONTENT",
          human_review_required: true,
          evidence_ids: ["leaf-c-stale-applicant-text-p1-1"],
          rule_ids: [],
          unsafe_false_negative: false,
          review_bypass: false,
          outside_represented_class: false,
          cost_usd: 0.02,
          latency_ms: 100,
          requests: 1,
          failure: null,
        },
      ],
    },
  ],
  demo_presets: [],
  graph_contract_disclosure:
    "Graph contract v2: FINDING -> CITES -> DOSSIER_EVIDENCE; FINDING -> ABOUT -> KEYWORD; DOSSIER_EVIDENCE -> OBSERVES -> KEYWORD.",
  correction_ledger_path: "data/presentation/m4/ledger.md",
};

const fixture = {
  id: "case-a-removed-3212",
  title: "Removed heading 3.2.S.1.2",
  description: "Primary Case A.",
  expected_class: "positive",
  archetype: "unavailable-heading",
  default_metadata_intent: null,
  manufacturer_partitioning: null,
  replacement_manufacturer_value: null,
  author_verified_relevant_hyperlink_ids: [],
};

afterEach(() => {
  cleanup();
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("M4 presentation dashboard and demo", () => {
  it("displays held-out repetitions, result statuses, safety caveat, retrieval, and provenance", async () => {
    window.history.pushState({}, "", "/evaluation");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ snapshot }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );

    render(<App />);

    expect(await screen.findByText(/held-out Phase 2 evaluation/i)).toBeVisible();
    expect(screen.getAllByText("live model output").length).toBeGreaterThan(0);
    expect(screen.getByText("genuine deterministic experimental output")).toBeVisible();
    expect(screen.getByText(/Zero unsafe-FNR does not establish safety/i)).toBeVisible();
    expect(screen.getByText("B1 BM25 retrieval metrics")).toBeVisible();
    expect(screen.getByText(/results are displayed, not recomputed/i)).toBeVisible();
    expect(screen.getByText(/expert_validated: false/i)).toBeVisible();
    expect(screen.getByText(/FINDING -> CITES -> DOSSIER_EVIDENCE/i)).toBeVisible();
  });

  it("resets the guided demo to the canonical preset and focus target", async () => {
    window.history.pushState({}, "", "/demo/case-a");
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.endsWith("/api/v1/fixtures")) {
          return Promise.resolve(new Response(JSON.stringify({ fixtures: [fixture] }), { status: 200 }));
        }
        if (url.endsWith("/api/v1/demo/presets")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                presets: [
                  {
                    id: "m4-case-a-primary",
                    route: "/demo/case-a",
                    label: "Case A primary",
                    fixture_id: "case-a-removed-3212",
                    purpose: "Identifier reuse.",
                    primary_path: true,
                    scenario_mode: "prospective_forward_compatibility",
                    metadata_plan: null,
                  },
                ],
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response("{}", { status: 200 }));
      }),
    );

    render(<App />);
    const currentOperational = await screen.findByLabelText("Current operational");
    fireEvent.click(currentOperational);
    fireEvent.click(screen.getByRole("button", { name: /Reset demo/i }));

    expect(screen.getByLabelText("Prospective research")).toBeChecked();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Parse and analyze/i })).toHaveFocus(),
    );
  });
});
