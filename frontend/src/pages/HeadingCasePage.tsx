import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Database,
  Flask,
  Restart,
  WarningTriangle,
} from "iconoir-react";

import { createAnalysis, getAnalysisGraph, getDemoPresets, getFixtures, parseFixture } from "../api/client";
import type {
  AnalysisResult,
  ApplicationInventory,
  DemoPreset,
  FixtureSummary,
  GraphNeighborhood as GraphData,
  ManufacturerPartitioning,
  MetadataIntent,
  ScenarioMode,
} from "../api/contracts";
import { Disclaimer } from "../components/Disclaimer";
import { GraphNeighborhood } from "../components/GraphNeighborhood";

const disclosure =
  "Prospective FDA/CDER forward-compatibility research scenario. FDA forward compatibility " +
  "is not operational, and this author-adjudicated demonstration is not regulatory-expert validated.";

const routeConfig = {
  "case-a": {
    archetype: "unavailable-heading",
    eyebrow: "M1 · unavailable target heading",
    title: "Inspect the placement. Follow the evidence. Preserve the document.",
    subtitle: "Run a controlled heading-placement scenario and inspect the evidence-backed decision trace.",
    control: "Choose a structural variant",
    demoRoute: "/demo/case-a",
  },
  "case-b": {
    archetype: "legacy-metadata-tension",
    eyebrow: "M2 · legacy metadata tension",
    title: "Declare the lifecycle intent. Keep the advisory visible.",
    subtitle: "Compare exact preservation, explicit normalization, and the abstention boundary for manufacturer metadata.",
    control: "Choose a metadata variant",
    demoRoute: "/demo/case-b",
  },
  "case-c": {
    archetype: "stale-content-or-hyperlink",
    eyebrow: "M2 · stale content or hyperlink",
    title: "Technical reuse can pass while the document is stale.",
    subtitle: "Inspect bounded PDF text and hyperlink evidence through the same production analysis path.",
    control: "Choose a semantic variant",
    demoRoute: "/demo/case-c",
  },
} as const;

export function HeadingCasePage() {
  const location = useLocation();
  const caseKey = location.pathname.endsWith("case-b")
    ? "case-b"
    : location.pathname.endsWith("case-c")
      ? "case-c"
      : "case-a";
  const config = routeConfig[caseKey];
  const [fixtures, setFixtures] = useState<FixtureSummary[]>([]);
  const [presets, setPresets] = useState<DemoPreset[]>([]);
  const [fixtureId, setFixtureId] = useState("");
  const [metadataIntent, setMetadataIntent] = useState<MetadataIntent>("unspecified");
  const [partitioning, setPartitioning] = useState<ManufacturerPartitioning>("unknown");
  const [replacementValue, setReplacementValue] = useState("");
  const [mode, setMode] = useState<ScenarioMode>("prospective_forward_compatibility");
  const [inventory, setInventory] = useState<ApplicationInventory | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const runButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    void Promise.all([getFixtures(), getDemoPresets()])
      .then(([fixtureResponse, presetResponse]) => {
        const matching = fixtureResponse.fixtures.filter((fixture) => fixture.archetype === config.archetype);
        const routePresets = presetResponse.presets ?? [];
        setPresets(routePresets);
        setFixtures(matching);
        const preset = routePresets.find((item) => item.route === config.demoRoute);
        const first = matching.find((item) => item.id === preset?.fixture_id) ?? matching[0];
        if (first) {
          setFixtureId(first.id);
          setMetadataIntent((preset?.metadata_plan?.intent as MetadataIntent | undefined) ?? first.default_metadata_intent ?? "unspecified");
          setPartitioning((preset?.metadata_plan?.manufacturer_partitioning as ManufacturerPartitioning | undefined) ?? first.manufacturer_partitioning ?? "unknown");
          setReplacementValue(preset?.metadata_plan?.replacement_manufacturer_value ?? first.replacement_manufacturer_value ?? "");
          setMode("prospective_forward_compatibility");
          setInventory(null);
          setAnalysis(null);
          setGraph(null);
        }
      })
      .catch((reason: Error) => setError(reason.message));
  }, [config.archetype, config.demoRoute]);

  function selectFixture(id: string, available = fixtures) {
    setFixtureId(id);
    const selected = available.find((fixture) => fixture.id === id);
    setMetadataIntent(selected?.default_metadata_intent ?? "unspecified");
    setPartitioning(selected?.manufacturer_partitioning ?? "unknown");
    setReplacementValue(selected?.replacement_manufacturer_value ?? "");
    setInventory(null);
    setAnalysis(null);
    setGraph(null);
  }

  function resetDemo() {
    const preset = presets.find((item) => item.route === config.demoRoute);
    const selected = fixtures.find((fixture) => fixture.id === preset?.fixture_id) ?? fixtures[0];
    if (selected) {
      setFixtureId(selected.id);
      setMetadataIntent((preset?.metadata_plan?.intent as MetadataIntent | undefined) ?? selected.default_metadata_intent ?? "unspecified");
      setPartitioning((preset?.metadata_plan?.manufacturer_partitioning as ManufacturerPartitioning | undefined) ?? selected.manufacturer_partitioning ?? "unknown");
      setReplacementValue(preset?.metadata_plan?.replacement_manufacturer_value ?? selected.replacement_manufacturer_value ?? "");
    }
    setMode("prospective_forward_compatibility");
    setInventory(null);
    setAnalysis(null);
    setGraph(null);
    setError(null);
    window.setTimeout(() => runButtonRef.current?.focus(), 0);
  }

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
      const metadataPlan = config.archetype === "legacy-metadata-tension" && leaf.keywords.some((item) => item.name === "manufacturer" && item.normalized_value === "all")
        ? {
            intent: metadataIntent,
            manufacturer_partitioning: partitioning,
            replacement_manufacturer_value: replacementValue.trim() || null,
          }
        : null;
      const result = await createAnalysis(parsed.id, leaf.id, mode, metadataPlan);
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
        <nav className="top-nav" aria-label="Primary navigation">
          <Link to="/">Scope</Link>
          <Link aria-current="page" to={config.demoRoute}>Demonstration</Link>
          <Link to="/evaluation">Evaluation</Link>
        </nav>
        <span className="operational-chip">not_operational</span>
      </header>

      <main id="main-content">
        <section className="case-hero">
          <Link className="back-link" to="/"><ArrowLeft aria-hidden="true" /> Research scope</Link>
          <div className="eyebrow"><Flask aria-hidden="true" /> {config.eyebrow}</div>
          <h1>{config.title}</h1>
          <p>{config.subtitle}</p>
        </section>
        <Disclaimer text={disclosure} />

        <section className="case-controls" aria-labelledby="case-controls-title">
          <div>
            <p className="panel-kicker">Controlled input</p>
            <h2 id="case-controls-title">{config.control}</h2>
          </div>
          <label>
            Controlled test case
            <select value={fixtureId} onChange={(event) => selectFixture(event.target.value)}>
              {fixtures.map((fixture) => (
                <option value={fixture.id} key={fixture.id}>{fixture.title}</option>
              ))}
            </select>
          </label>
          {config.archetype === "legacy-metadata-tension" && (
            <label className="conditional-control">
              Metadata intent
              <select value={metadataIntent} onChange={(event) => setMetadataIntent(event.target.value as MetadataIntent)}>
                <option value="preserve-existing-lifecycle">Preserve existing lifecycle</option>
                <option value="normalize-metadata">Normalize metadata</option>
                <option value="unspecified">Unspecified</option>
              </select>
            </label>
          )}
          {config.archetype === "legacy-metadata-tension" && metadataIntent === "normalize-metadata" && (
            <label className="conditional-control">
              Manufacturer partitioning
              <select value={partitioning} onChange={(event) => setPartitioning(event.target.value as ManufacturerPartitioning)}>
                <option value="unnecessary">Unnecessary - omit keyword</option>
                <option value="required">Required - supply stable value</option>
                <option value="unknown">Unknown - request review</option>
              </select>
            </label>
          )}
          {metadataIntent === "normalize-metadata" && partitioning === "required" && (
            <label className="conditional-control">
              Stable manufacturer value
              <input value={replacementValue} onChange={(event) => setReplacementValue(event.target.value)} />
            </label>
          )}
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
          <button className="secondary-button" type="button" onClick={resetDemo} disabled={!fixtures.length}>
            <Restart aria-hidden="true" /> Reset demo
          </button>
          <button ref={runButtonRef} className="primary-button" type="button" onClick={() => void runAnalysis()} disabled={busy || !fixtures.length}>
            {busy ? "Analyzing…" : "Parse and analyze"}<ArrowRight aria-hidden="true" />
          </button>
        </section>

        {error && <div className="inline-error" role="alert"><WarningTriangle aria-hidden="true" />{error}</div>}

        {inventory && selectedLeaf && (
          <section className="inventory-strip motion-enter" aria-label="Parsed legacy artifact">
            <Database aria-hidden="true" />
            <div><span>Leaf</span><strong>{selectedLeaf.id}</strong></div>
            <div><span>Heading</span><strong>{selectedLeaf.heading}</strong></div>
            <div><span>Operation</span><strong>{selectedLeaf.operation}</strong></div>
            <div><span>PDF evidence</span><strong>{selectedLeaf.text_span_count} text · {selectedLeaf.hyperlink_count} links · {selectedLeaf.extraction_status}</strong></div>
            {selectedLeaf.keywords.map((keyword) => <div key={keyword.name}><span>{keyword.name}</span><strong>{keyword.raw_value}</strong></div>)}
            <div><span>Package digest</span><code>{inventory.package_sha256.slice(0, 16)}…</code></div>
          </section>
        )}

        {analysis && (
          <div className="analysis-results motion-enter" aria-live="polite" ref={resultsRef} tabIndex={-1}>
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

            <section className="result-section" aria-labelledby="findings-title">
              <p className="panel-kicker">Observed, deterministic, and semantic</p>
              <h2 id="findings-title">Triggered findings</h2>
              <div className="finding-list">
                {analysis.findings.map((finding) => (
                  <article key={finding.id}>
                    <strong>{finding.source.replaceAll("_", " ")} · {finding.enforcement_mode}</strong>
                    <p>{finding.rationale}</p>
                    <span>{finding.verification_basis} · {finding.severity}</span>
                  </article>
                ))}
                {!analysis.findings.length && <p>No material finding was returned.</p>}
              </div>
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
                    {"source_id" in item ? (
                      <><p>{item.source_id} · {item.bindingness} · {item.review_status} · expert validated: no</p><code>{item.source_sha256}</code></>
                    ) : (
                      <><p>Dossier {item.kind} · deterministic extraction</p><code>{item.file_sha256}</code></>
                    )}
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

            <section className="result-section" aria-labelledby="graph-contract-built-title">
              <p className="panel-kicker">Built graph contract</p>
              <h2 id="graph-contract-built-title">Occurrence evidence remains the cited object</h2>
              <p>
                M4 displays graph schema v2 as implemented: FINDING cites DOSSIER_EVIDENCE,
                FINDING is about KEYWORD, and DOSSIER_EVIDENCE observes KEYWORD. The planned
                discriminated evidence union was replaced by one occurrence node type plus evidence_kind.
              </p>
            </section>

            <section className="result-section model-run" aria-label="Semantic inspection record">
              <p className="panel-kicker">Evidence-bounded model record</p>
              <h2>Semantic inspection: {analysis.model_run.status}</h2>
              <p>{analysis.model_run.mode} mode · prompt {analysis.model_run.prompt_template_version} · {Math.round(analysis.model_run.latency_ms)} ms</p>
              {analysis.model_run.validation_error && <p>Validation error: {analysis.model_run.validation_error}</p>}
            </section>

            <section className="result-section" aria-labelledby="trace-title">
              <p className="panel-kicker">Machine-readable trace</p>
              <h2 id="trace-title">Chronological analysis trace</h2>
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
