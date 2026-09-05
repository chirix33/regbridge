import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Database, Filter, NavArrowLeft, WarningTriangle } from "iconoir-react";

import { getM3Presentation } from "../api/client";
import type { PresentationCaseTrace, PresentationMetricReport } from "../api/contracts";

function formatRate(rate: number | null): string {
  return rate === null ? "n/a" : `${Math.round(rate * 1000) / 10}%`;
}

function formatMetric(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(3);
}

function rateWithCounts(metric: PresentationMetricReport["unsafe_false_negative_rate"]): string {
  return `${metric.numerator}/${metric.denominator} (${formatRate(metric.rate)})`;
}

function repetitionLabel(value: number | null): string {
  return value === null ? "rule-only" : `rep ${value}`;
}

export function EvaluationDashboard() {
  const presentation = useQuery({ queryKey: ["m4-presentation"], queryFn: getM3Presentation });
  const [systemFilter, setSystemFilter] = useState("all");
  const [familyFilter, setFamilyFilter] = useState("all");
  const [caseFilter, setCaseFilter] = useState("all");

  const snapshot = presentation.data?.snapshot;
  const families = useMemo(
    () => Array.from(new Set(snapshot?.cases.map((item) => item.fixture_family) ?? [])).sort(),
    [snapshot],
  );

  const reports = useMemo(() => {
    const allReports = snapshot?.metric_reports ?? [];
    return allReports.filter((report) => systemFilter === "all" || report.system === systemFilter);
  }, [snapshot, systemFilter]);

  const cases = useMemo(() => {
    const allCases = snapshot?.cases ?? [];
    return allCases.filter(
      (item) =>
        (familyFilter === "all" || item.fixture_family === familyFilter) &&
        (caseFilter === "all" || item.case_id === caseFilter),
    );
  }, [snapshot, familyFilter, caseFilter]);

  if (presentation.isPending) {
    return (
      <main className="state-panel" aria-live="polite">
        <Database aria-hidden="true" />
        <p>Loading frozen Phase 2 presentation snapshot...</p>
      </main>
    );
  }

  if (presentation.isError || !snapshot) {
    return (
      <main className="state-panel error-state" role="alert">
        <WarningTriangle aria-hidden="true" />
        <h1>Presentation snapshot unavailable</h1>
        <p>Generate or validate the M4 snapshot, then reload the dashboard.</p>
      </main>
    );
  }

  // When a filter narrows the list, the operator asked for those cases: show
  // their predictions without a second click.
  const isNarrowed = familyFilter !== "all" || caseFilter !== "all";

  return (
    <div className="app-shell dashboard-shell">
      <main id="main-content">
        <section className="dashboard-hero">
          <Link className="back-link" to="/about">
            <NavArrowLeft aria-hidden="true" /> Research scope
          </Link>
          <p className="panel-kicker">M4 comparison dashboard</p>
          <h1>Held-out Phase 2 evaluation, displayed from an immutable snapshot.</h1>
          <p>{snapshot.disclosure}</p>
          <div className="digest-row" aria-label="Snapshot provenance">
            <span>Snapshot {snapshot.snapshot_version}</span>
            <span>Run {snapshot.source_run_id}</span>
            <span>Digest {snapshot.snapshot_sha256.slice(0, 16)}...</span>
          </div>
        </section>

        <section className="operational-banner" aria-label="Research and operational disclosures">
          <WarningTriangle aria-hidden="true" />
          <div>
            <strong>FDA forward compatibility: {snapshot.current_fda_operational_availability}</strong>
            <span>Prospective FDA/CDER scenario · expert_validated: false · live outputs are not output-deterministic</span>
          </div>
        </section>

        <section className="dashboard-grid" aria-label="Evaluation summary">
          <article className="metric-panel safety-panel">
            <p className="panel-kicker">Safety summary</p>
            <h2>Unsafe FNR and review bypass are co-primary display checks</h2>
            <p>
              Zero unsafe-FNR does not establish safety when unconditional legacy reuse was never predicted.
              Wilson values are descriptive; clustered intervals are exploratory with no independence or
              significance claim.
            </p>
          </article>
          <article className="metric-panel">
            <p className="panel-kicker">Cost</p>
            <h2>${Number(snapshot.cost_summary.total_cost_usd).toFixed(3)}</h2>
            <p>Total recorded Phase 2 live-model cost. B2 made no model calls.</p>
          </article>
          <article className="metric-panel">
            <p className="panel-kicker">Completion audit</p>
            <h2>{String(snapshot.completion_audit.completed_outcomes)}/{String(snapshot.completion_audit.scheduled_outcomes)}</h2>
            <p>{String(snapshot.completion_audit.state)} · {String(snapshot.completion_audit.stop_reason)}</p>
          </article>
        </section>

        <section className="result-section" aria-labelledby="metrics-title">
          <div className="section-toolbar">
            <div>
              <p className="panel-kicker">Per repetition</p>
              <h2 id="metrics-title">Decision metrics</h2>
            </div>
            <label className="compact-filter">
              <Filter aria-hidden="true" />
              System
              <select value={systemFilter} onChange={(event) => setSystemFilter(event.target.value)}>
                <option value="all">All systems</option>
                <option value="B0">B0</option>
                <option value="B1">B1</option>
                <option value="B2">B2</option>
                <option value="RegBridge">RegBridge</option>
              </select>
            </label>
          </div>
          <div className="table-scroll motion-filter" role="region" aria-label="Decision metrics table" tabIndex={0} key={systemFilter}>
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>System</th>
                  <th>Repetition</th>
                  <th>Result status</th>
                  <th>Accuracy</th>
                  <th>Macro-F1</th>
                  <th>Unsafe FNR</th>
                  <th>Review bypass</th>
                  <th>Outside class</th>
                  <th>Invalid</th>
                  <th>Requests</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={`${report.system}-${report.repetition_index ?? "b2"}`}>
                    <td>{report.system}</td>
                    <td>{repetitionLabel(report.repetition_index)}</td>
                    <td>{report.result_status}</td>
                    <td>{formatMetric(report.accuracy)}</td>
                    <td>{formatMetric(report.macro_f1)}</td>
                    <td>{rateWithCounts(report.unsafe_false_negative_rate)}</td>
                    <td>{rateWithCounts(report.review_bypass_rate)}</td>
                    <td>{formatRate(report.outside_represented_rate)}</td>
                    <td>{report.invalid_outputs} ({formatRate(report.invalid_output_rate)})</td>
                    <td>{report.requests}</td>
                    <td>{report.cost_usd === null ? "n/a" : `$${report.cost_usd.toFixed(3)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {snapshot.retrieval_summary && (
          <section className="result-section" aria-labelledby="retrieval-title">
            <p className="panel-kicker">Measured retrieval only</p>
            <h2 id="retrieval-title">B1 BM25 retrieval metrics</h2>
            <div className="retrieval-grid">
              {snapshot.retrieval_summary.per_repetition.map((item) => (
                <article key={item.repetition_index}>
                  <strong>rep {item.repetition_index}</strong>
                  <span>recall@3 {formatMetric(item.recall_at_3)}</span>
                  <span>precision@3 {formatMetric(item.precision_at_3)}</span>
                  <span>MRR {formatMetric(item.mrr)}</span>
                  <small>{snapshot.retrieval_summary?.result_status}</small>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className="result-section" aria-labelledby="cases-title">
          <div className="section-toolbar">
            <div>
              <p className="panel-kicker">Per-case trace</p>
              <h2 id="cases-title">Held-out case drill-down</h2>
            </div>
            <div className="filter-row">
              <label className="compact-filter">
                Family
                <select value={familyFilter} onChange={(event) => setFamilyFilter(event.target.value)}>
                  <option value="all">All families</option>
                  {families.map((family) => <option key={family} value={family}>{family}</option>)}
                </select>
              </label>
              <label className="compact-filter">
                Case
                <select value={caseFilter} onChange={(event) => setCaseFilter(event.target.value)}>
                  <option value="all">All cases</option>
                  {snapshot.cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id}</option>)}
                </select>
              </label>
            </div>
          </div>
          <div className="case-trace-list motion-filter" key={`${familyFilter}-${caseFilter}`}>
            {cases.map((item) => <CaseTraceCard key={item.case_id} item={item} defaultOpen={isNarrowed} />)}
          </div>
        </section>

        <section className="result-section" aria-labelledby="graph-contract-title">
          <p className="panel-kicker">Graph explanation contract</p>
          <h2 id="graph-contract-title">Displayed as built</h2>
          <p>{snapshot.graph_contract_disclosure}</p>
          <p className="digest">Prompt digest {snapshot.frozen_prompt_digest}</p>
          <p className="digest">Configuration digest {snapshot.frozen_configuration_digest}</p>
        </section>
      </main>
    </div>
  );
}

function CaseTraceCard({ item, defaultOpen }: { item: PresentationCaseTrace; defaultOpen: boolean }) {
  return (
    <article className="case-trace-card">
      <div className="case-trace-heading">
        <div>
          <h3>{item.case_id} · {item.fixture_family}</h3>
          <p>{item.archetype} · reference {item.reference_decision.replaceAll("_", " ")}</p>
        </div>
        <span className={item.varied_predictions ? "status-pill warning" : "status-pill"}>
          {item.varied_predictions ? "varied across repetitions" : "stable display trace"}
        </span>
      </div>
      <details className="case-trace-toggle" open={defaultOpen}>
        <summary>
          {item.predictions.length} system prediction{item.predictions.length === 1 ? "" : "s"}
        </summary>
        <div
          className="table-scroll"
          role="region"
          aria-label={`${item.case_id} system predictions`}
          tabIndex={0}
        >
        <table className="metrics-table compact">
          <thead>
            <tr>
              <th>System</th>
              <th>Rep</th>
              <th>Predicted decision</th>
              <th>Action</th>
              <th>Unsafe miss</th>
              <th>Review bypass</th>
              <th>Outside class</th>
              <th>Evidence IDs</th>
            </tr>
          </thead>
          <tbody>
            {item.predictions.map((prediction) => (
              <tr key={`${prediction.system}-${prediction.repetition_index ?? "b2"}`}>
                <td>{prediction.system}</td>
                <td>{repetitionLabel(prediction.repetition_index)}</td>
                <td>{prediction.decision.replaceAll("_", " ")}</td>
                <td>{prediction.action}</td>
                <td>{prediction.unsafe_false_negative ? "yes" : "no"}</td>
                <td>{prediction.review_bypass ? "yes" : "no"}</td>
                <td>{prediction.outside_represented_class ? "yes" : "no"}</td>
                <td>{prediction.evidence_ids.join(", ") || "none"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </details>
    </article>
  );
}
