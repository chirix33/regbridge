import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Book,
  CheckCircle,
  Database,
  Flask,
  OpenNewWindow,
  WarningTriangle,
} from "iconoir-react";

import { getScope, getStandardsSnapshot } from "../api/client";
import { Disclaimer } from "../components/Disclaimer";

const archetypeLabels: Record<string, string> = {
  "unavailable-heading": "Unavailable target heading",
  "legacy-metadata-tension": "Legacy metadata tension",
  "stale-content-or-hyperlink": "Stale content or hyperlink",
};

export function ScopePage() {
  const scope = useQuery({ queryKey: ["scope"], queryFn: getScope });
  const standards = useQuery({ queryKey: ["standards"], queryFn: getStandardsSnapshot });

  if (scope.isPending || standards.isPending) {
    return (
      <main className="state-panel" aria-live="polite">
        <Flask aria-hidden="true" />
        <p>Loading the source-verified research scope…</p>
      </main>
    );
  }

  if (scope.isError || standards.isError) {
    return (
      <main className="state-panel error-state" role="alert">
        <WarningTriangle aria-hidden="true" />
        <h1>Scope data is unavailable</h1>
        <p>Start the local RegBridge API, then reload this page.</p>
      </main>
    );
  }

  const scopeData = scope.data;
  const snapshot = standards.data;

  return (
    <div className="app-shell">

      <main id="main-content">
        <div className="page-context">
          <div className="status-chip">
            <span className="status-dot" aria-hidden="true" />
            {scopeData.model_mode === "fixture" ? "Offline fixture mode" : `${scopeData.model_mode} mode`}
          </div>
        </div>
        <section className="hero" aria-labelledby="hero-title">
          <div className="eyebrow">
            <Flask aria-hidden="true" width={18} height={18} />
            FDA / CDER research prototype
          </div>
          <h1 id="hero-title">
            Technical referenceability is only the start. <em>Evidence decides reuse.</em>
          </h1>
          <p className="hero-copy">{scopeData.research_question}</p>
          <div className="scope-line" aria-label="Current analysis scope">
            <span>{scopeData.source_standards.join(", ")}</span>
            <ArrowRight aria-hidden="true" />
            <span>{scopeData.target_standards.join(", ")}</span>
            <span className="scope-divider" aria-hidden="true" />
            <span>{scopeData.authority} / {scopeData.center}</span>
            <span className="scope-divider" aria-hidden="true" />
            <span>{scopeData.supported_application_types.join(", ")}</span>
          </div>
        </section>

        <Disclaimer text={scopeData.disclaimer} />

        <section className="operational-banner" aria-label="FDA operational availability">
          <WarningTriangle aria-hidden="true" />
          <div>
            <strong>FDA forward compatibility: {scopeData.operational_status}</strong>
            <span>
              M1/M2 are clearly labeled prospective research scenarios · expert validated: no
            </span>
          </div>
          <Link className="primary-link" to="/demo/case-a">
            Open shared analyzer <ArrowRight aria-hidden="true" />
          </Link>
        </section>

        <section className="content-grid" aria-label="M0 capabilities and provenance">
          <article className="panel archetype-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Planned demonstration</p>
                <h2>Three risks, one analysis contract</h2>
              </div>
              <CheckCircle aria-hidden="true" />
            </div>
            <ol className="archetype-list">
              {scopeData.planned_archetypes.map((archetype, index) => (
                <li key={archetype}>
                  <span className="step-number">0{index + 1}</span>
                  <div>
                    <strong>{archetypeLabels[archetype] ?? archetype}</strong>
                    <span>{index === 0 ? "M1 implemented" : "M2 implemented"}</span>
                  </div>
                </li>
              ))}
            </ol>
          </article>

          <article className="panel source-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Pinned evidence</p>
                <h2>Source-verified registry</h2>
              </div>
              <Database aria-hidden="true" />
            </div>
            {snapshot.sources.length ? (
              <div className="source-stack">
                {snapshot.sources.map((source) => (
                  <div className="source-card" key={source.id}>
                    <div className="source-meta">
                      <span>{source.review_status}</span>
                      <span>{source.version}</span>
                    </div>
                    <h3>{source.title}</h3>
                    <p>Snapshot <code>{snapshot.snapshot_id}</code></p>
                    <p className="digest">SHA-256 {source.sha256}</p>
                    <a href={source.source_url} target="_blank" rel="noreferrer">
                      Open official FDA source
                      <OpenNewWindow aria-hidden="true" width={16} height={16} />
                    </a>
                  </div>
                ))}
              </div>
            ) : (
              <p>No source-verified source is registered.</p>
            )}
          </article>
        </section>

        <section className="boundary" aria-labelledby="boundary-title">
          <Book aria-hidden="true" />
          <div>
            <p className="panel-kicker">Current milestone boundary</p>
            <h2 id="boundary-title">All three archetypes share one analyzer path.</h2>
            <p>
              M2 adds lifecycle-sensitive metadata constraints, bounded PDF text and hyperlink
              extraction, evidence-bounded semantic inspection, deterministic precedence, and
              persistent traces. FDA forward compatibility remains not operational.
            </p>
            <div className="workspace-links">
              <Link to="/demo/case-a">Heading case</Link>
              <Link to="/demo/case-b">Metadata case</Link>
              <Link to="/demo/case-c">Semantic PDF case</Link>
              <Link to="/evaluation">Evaluation dashboard</Link>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <span>RegBridge · decision support, not regulatory advice</span>
        <span>{scopeData.network_required ? "Network-backed model" : "No network or model key required"}</span>
      </footer>
    </div>
  );
}
