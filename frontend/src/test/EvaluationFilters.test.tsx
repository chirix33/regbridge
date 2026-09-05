import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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


afterEach(() => {
  cleanup();
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// The dashboard fixture ships a single case, which cannot show the difference
// between a narrowed and an unnarrowed list. Add a second case in a second
// family so both drill-down filters have something to remove.
const secondCase = {
  ...snapshot.cases[0],
  case_id: "A001",
  fixture_id: "case-a-removed-3212",
  fixture_family: "a-removed-3212-lifecycle",
  archetype: "unavailable-heading",
  reference_decision: "REUSE_WITH_NEW_CONTEXT",
  varied_predictions: false,
};
const filterableSnapshot = { ...snapshot, cases: [snapshot.cases[0], secondCase] };

// App.tsx holds a module-level QueryClient with a 60s staleTime, so a snapshot
// cached by one test file would be served to another. Vitest isolates modules
// per file, which is why this suite lives outside M4Presentation.test.tsx.
function renderDashboard() {
  window.history.pushState({}, "", "/evaluation");
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ snapshot: filterableSnapshot }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    ),
  );
  render(<App />);
}

function caseTraceToggles(): HTMLDetailsElement[] {
  return Array.from(document.querySelectorAll("details.case-trace-toggle"));
}

function firstToggle(): HTMLDetailsElement {
  const [toggle] = caseTraceToggles();
  if (!toggle) {
    throw new Error("expected at least one case-trace disclosure to be rendered");
  }
  return toggle;
}

describe("per-case trace expansion follows the drill-down filters", () => {
  it("keeps every trace collapsed until a filter narrows the list", async () => {
    renderDashboard();
    await screen.findByText(/held-out Phase 2 evaluation/i);

    expect(caseTraceToggles()).toHaveLength(2);
    expect(caseTraceToggles().some((toggle) => toggle.open)).toBe(false);
  });

  it("opens the remaining traces when the family filter narrows the list", async () => {
    renderDashboard();
    await screen.findByText(/held-out Phase 2 evaluation/i);

    fireEvent.change(screen.getByLabelText(/Family/i), {
      target: { value: "a-removed-3212-lifecycle" },
    });

    expect(caseTraceToggles()).toHaveLength(1);
    expect(firstToggle().open).toBe(true);
  });

  it("opens the remaining traces when the case filter narrows the list", async () => {
    renderDashboard();
    await screen.findByText(/held-out Phase 2 evaluation/i);

    fireEvent.change(screen.getByLabelText(/^Case$/i), { target: { value: "C002" } });

    expect(caseTraceToggles()).toHaveLength(1);
    expect(firstToggle().open).toBe(true);
  });

  it("collapses the traces again when the filters are cleared", async () => {
    renderDashboard();
    await screen.findByText(/held-out Phase 2 evaluation/i);

    const family = screen.getByLabelText(/Family/i);
    fireEvent.change(family, { target: { value: "a-removed-3212-lifecycle" } });
    expect(firstToggle().open).toBe(true);

    fireEvent.change(family, { target: { value: "all" } });

    expect(caseTraceToggles()).toHaveLength(2);
    expect(caseTraceToggles().some((toggle) => toggle.open)).toBe(false);
  });

  it("lets the operator collapse a narrowed trace and keeps it collapsed", async () => {
    renderDashboard();
    await screen.findByText(/held-out Phase 2 evaluation/i);

    fireEvent.change(screen.getByLabelText(/Family/i), {
      target: { value: "a-removed-3212-lifecycle" },
    });
    const toggle = firstToggle();
    expect(toggle.open).toBe(true);

    toggle.open = false;
    fireEvent(toggle, new Event("toggle"));

    // A later re-render that does not remount the card must not force it open.
    const systemFilter = document.querySelector<HTMLSelectElement>(
      '[aria-labelledby="metrics-title"] select',
    );
    if (!systemFilter) {
      throw new Error("expected the decision-metrics system filter to be rendered");
    }
    fireEvent.change(systemFilter, { target: { value: "B0" } });

    expect(firstToggle().open).toBe(false);
  });
});
