import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Database,
  Flask,
  WarningTriangle,
} from "iconoir-react";

import { createAnalysis, getAnalysisGraph, getFixtures, parseFixture } from "../api/client";
import type {
  AnalysisResult,
  ApplicationInventory,
  FixtureSummary,
  GraphNeighborhood as GraphData,
  ScenarioMode,
} from "../api/contracts";
import { Disclaimer } from "../components/Disclaimer";
import { GraphNeighborhood } from "../components/GraphNeighborhood";

const disclosure =
  "Prospective FDA/CDER forward-compatibility research scenario. FDA forward compatibility " +
  "is not operational, and this author-adjudicated demonstration is not regulatory-expert validated.";

const subtitle =
  "Run a controlled heading-placement scenario and inspect the evidence-backed decision trace.";

export function HeadingCasePage() {
  const [fixtures, setFixtures] = useState<FixtureSummary[]>([]);
  const [fixtureId, setFixtureId] = useState("case-a-removed-3211");
  const [mode, setMode] = useState<ScenarioMode>("prospective_forward_compatibility");
  const [inventory, setInventory] = useState<ApplicationInventory | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void getFixtures().then((response) => setFixtures(response.fixtures)).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!analysis || !resultsRef.current) {
      return;
    }
    resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    resultsRef.current.focus({ preventScroll: true });
  }, [analysis]);

  async function runAnalysis() {
    setBusy(true);
    setError(null);
    setAnalysis(null);
    setGraph(null);
    try {
      const parsed = await parseFixture(fixtureId);
      setInventory(parsed);
      const leaf = parsed.leaves[0];
      if (!leaf) {
        throw new Error("The parsed package contains no analyzable leaf.");
      }
      const result = await createAnalysis(parsed.id, leaf.id, mode);
      setAnalysis(result);
      setGraph(await getAnalysisGraph(result.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  const selectedLeaf = inventory?.leaves[0];

  return (
    <div className="app-shell case-shell">
      <header className="site-header">
        <Link className="brand" to="/">
          <span className="brand-mark" aria-hidden="true">R</span>
          <span>RegBridge</span>
        </Link>
        <span className="operational-chip">not_operational</span>
      </header>

      <main id="main-content">
        <section className="case-hero">
          <Link className="back-link" to="/"><ArrowLeft aria-hidden="true" /> Research scope</Link>
          <div className="eyebrow"><Flask aria-hidden="true" /> M1 · unavailable target heading</div>
          <h1>Inspect the placement. Follow the evidence. Preserve the document.</h1>
          <p>{subtitle}</p>
        </section>
        <Disclaimer text={disclosure} />

        <section className="case-controls" aria-labelledby="case-controls-title">
          <div>
            <p className="panel-kicker">Controlled input</p>
            <h2 id="case-controls-title">Choose a structural variant</h2>
          </div>
          <label>
            Controlled test case
            <select value={fixtureId} onChange={(event) => setFixtureId(event.target.value)}>
              {fixtures.map((fixture) => (
                <option value={fixture.id} key={fixture.id}>{fixture.title}</option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Analysis mode</legend>
            <label>
              <input
                type="radio"
                name="mode"
                checked={mode === "prospective_forward_compatibility"}
                onChange={() => setMode("prospective_forward_compatibility")}
              />
              Prospective research
            </label>
            <label>
              <input
                type="radio"
                name="mode"
                checked={mode === "current_operational"}
                onChange={() => setMode("current_operational")}
              />
              Current operational
            </label>
          </fieldset>
          <button className="primary-button" type="button" onClick={() => void runAnalysis()} disabled={busy || !fixtures.length}>
            {busy ? "Analyzing…" : "Parse and analyze"}<ArrowRight aria-hidden="true" />
          </button>
        </section>

        {error && <div className="inline-error" role="alert"><WarningTriangle aria-hidden="true" />{error}</div>}

        {inventory && selectedLeaf && (
          <section className="inventory-strip" aria-label="Parsed legacy artifact">
            <Database aria-hidden="true" />
            <div><span>Leaf</span><strong>{selectedLeaf.id}</strong></div>
            <div><span>Heading</span><strong>{selectedLeaf.heading}</strong></div>
            <div><span>Operation</span><strong>{selectedLeaf.operation}</strong></div>
            <div><span>Package digest</span><code>{inventory.package_sha256.slice(0, 16)}…</code></div>
          </section>
        )}

        {analysis && (
          <div className="analysis-results" aria-live="polite" ref={resultsRef} tabIndex={-1}>
            <section className={`decision-card severity-${analysis.severity}`}>
              <div>
                <p className="panel-kicker">Decision · {analysis.severity}</p>
                <h2>{analysis.decision.replaceAll("_", " ")}</h2>
                <p>{analysis.rationale}</p>
              </div>
              <CheckCircle aria-hidden="true" />
              <dl>
                <div><dt>Operational status</dt><dd>{analysis.operational_status}</dd></div>
                <div><dt>Expert validated</dt><dd>{analysis.expert_validated ? "yes" : "no"}</dd></div>
                <div><dt>Confidence</dt><dd>{Math.round(analysis.confidence * 100)}%</dd></div>
                <div><dt>Human approval</dt><dd>{analysis.human_approval_required ? "required" : "not required"}</dd></div>
              </dl>
            </section>

            <section className="result-section repair-section">
              <p className="panel-kicker">Minimum repair</p>
              <h2>{analysis.repair.type.replaceAll("_", " ")}</h2>
              <p>{analysis.repair.description}</p>
            </section>

            <section className="result-section" aria-labelledby="evidence-title">
              <div className="result-heading">
                <p className="panel-kicker">Source-verified support</p>
                <h2 id="evidence-title">Evidence spans</h2>
              </div>
              <div className="evidence-grid">
                {analysis.evidence.map((item) => (
                  <details className="evidence-card" key={item.id}>
                    <summary>{item.locator}</summary>
                    <blockquote>{item.text}</blockquote>
                    <p>{item.source_id} · {item.review_status} · expert validated: no</p>
                    <code>{item.source_sha256}</code>
                  </details>
                ))}
                {!analysis.evidence.length && <p>FDA forward compatibility is currently unavailable in current operational mode.</p>}
              </div>
            </section>

            {analysis.unresolved_uncertainty.length > 0 && (
              <section className="inline-error" aria-label="Unresolved uncertainty">
                <WarningTriangle aria-hidden="true" />
                <div>{analysis.unresolved_uncertainty.map((item) => <p key={item}>{item}</p>)}</div>
              </section>
            )}

            {graph && <GraphNeighborhood graph={graph} />}

            <section className="result-section" aria-labelledby="trace-title">
              <p className="panel-kicker">Machine-readable trace</p>
              <h2 id="trace-title">Deterministic steps</h2>
              <ol className="trace-list">
                {analysis.trace.map((step) => (
                  <li key={step.sequence}><span>{step.sequence}</span><div><strong>{step.component}</strong><p>{step.summary}</p></div></li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
