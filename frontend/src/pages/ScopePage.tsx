import { useQuery } from "@tanstack/react-query";
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
        <p>Loading the reviewed research scope…</p>
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
  const source = snapshot.sources[0];

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#main-content" aria-label="RegBridge home">
          <span className="brand-mark" aria-hidden="true">
            R
          </span>
          <span>RegBridge</span>
        </a>
        <div className="status-chip">
          <span className="status-dot" aria-hidden="true" />
          {scopeData.model_mode === "fixture" ? "Offline fixture mode" : `${scopeData.model_mode} mode`}
        </div>
      </header>

      <main id="main-content">
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
                    <span>{index === 0 ? "Begins in M1" : "Scheduled for M2"}</span>
                  </div>
                </li>
              ))}
            </ol>
          </article>

          <article className="panel source-panel">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Pinned evidence</p>
                <h2>Reviewed source registry</h2>
              </div>
              <Database aria-hidden="true" />
            </div>
            {source ? (
              <div className="source-card">
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
            ) : (
              <p>No reviewed source is registered.</p>
            )}
          </article>
        </section>

        <section className="boundary" aria-labelledby="boundary-title">
          <Book aria-hidden="true" />
          <div>
            <p className="panel-kicker">Current milestone boundary</p>
            <h2 id="boundary-title">Contracts and provenance are live. Decisions are not.</h2>
            <p>
              M0 establishes typed outputs, validated configuration, immutable source metadata,
              and deterministic model fixtures. No artifact reuse decision is produced until the
              M1 parser, graph facts, reviewed evidence spans, and constraints are connected.
            </p>
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

