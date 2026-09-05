import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Database, Upload, WarningTriangle } from "iconoir-react";

import { createDossierAnalysis, getDossierAnalysis, getModels, getProductDemoPackage, parseUpload } from "../api/client";
import type { ApplicationInventory, DossierAnalysisRun, MetadataIntent, TargetContext } from "../api/contracts";
import { GraphNeighborhood } from "../components/GraphNeighborhood";

function target(intent: MetadataIntent, scenario: TargetContext["scenario_mode"]): TargetContext {
  return {
    authority: "FDA", center: "CDER", application_type: "NDA", source_standard: "eCTD-3.2.2",
    target_standard: "eCTD-4.0", analysis_date: new Date().toISOString().slice(0, 10),
    reuse_operation: "reference-existing-content", standards_snapshot_id: "fda-cder-demo-v1",
    scenario_mode: scenario,
    metadata_plan: { intent, manufacturer_partitioning: "unknown", replacement_manufacturer_value: null },
  };
}

export function DossierWorkspace() {
  const models = useQuery({ queryKey: ["models"], queryFn: getModels });
  const [file, setFile] = useState<File | null>(null);
  const [inventory, setInventory] = useState<ApplicationInventory | null>(null);
  const [run, setRun] = useState<DossierAnalysisRun | null>(null);
  const [modelId, setModelId] = useState("gpt-5.5");
  const [intent, setIntent] = useState<MetadataIntent>("preserve-existing-lifecycle");
  const [scenario, setScenario] = useState<TargetContext["scenario_mode"]>("prospective_forward_compatibility");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openLeaf, setOpenLeaf] = useState<string | null>(null);
  const terminal = run && ["completed", "partial_failed", "failed"].includes(run.state);

  useEffect(() => {
    if (!run || terminal) return;
    const timer = window.setInterval(() => getDossierAnalysis(run.run_id).then(setRun).catch((cause: Error) => setError(cause.message)), 700);
    return () => window.clearInterval(timer);
  }, [run, terminal]);

  const selectedProfile = useMemo(
    () => models.data?.models?.find((item) => item.model_id === modelId),
    [models.data, modelId],
  );

  async function submit() {
    if (!file || !confirmed || selectedProfile?.availability !== "available") return;
    setBusy(true); setError(null); setRun(null);
    try {
      const parsed = await parseUpload(file);
      setInventory(parsed);
      sessionStorage.setItem("regbridge.inventory", JSON.stringify(parsed));
      const created = await createDossierAnalysis(parsed.id, modelId, target(intent, scenario));
      setRun(created);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Analysis failed"); }
    finally { setBusy(false); }
  }

  return (
    <main className="product-workspace" id="main-content">
      <section className="workspace-hero"><p className="eyebrow">End-to-end dossier workspace</p><h1>Inspect reuse risk from the package itself.</h1><p>Upload a public, synthetic, or deliberately de-identified controlled dossier. XML, regional metadata, lifecycle fields, checksums, and PDF evidence drive the result.</p></section>
      <section className="boundary-banner" aria-label="Research boundary"><WarningTriangle aria-hidden="true"/><div><strong>FDA/CDER prospective research prototype · not_operational</strong><span>expert_validated: false · no FDA acceptance, compliance, readiness, or regulatory-advice claim</span></div></section>
      <section className="workspace-grid">
        <form className="panel upload-panel" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <h2><Upload aria-hidden="true"/> Upload and analyze</h2>
          <button type="button" onClick={() => { void getProductDemoPackage().then(setFile).catch((cause: Error) => setError(cause.message)); }}>Load M4.2 demo preset</button>
          {file && <p className="field-note">Selected: {file.name}</p>}
          <label>Dossier ZIP<input aria-label="Dossier ZIP" type="file" accept=".zip,application/zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
          <label>Available LLM<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.data?.models.map((profile) => <option key={profile.model_id} value={profile.model_id} disabled={profile.availability !== "available"}>{profile.display_name}{profile.availability !== "available" ? " — disabled" : ""}</option>)}</select></label>
          {models.data?.models.filter((item) => item.availability !== "available").map((item) => <p className="field-note" key={item.model_id}>{item.display_name}: {item.disabled_reason}</p>)}
          <fieldset><legend>Target context</legend><dl className="context-list"><div><dt>Authority / center</dt><dd>FDA / CDER</dd></div><div><dt>Application</dt><dd>NDA</dd></div><div><dt>Transition</dt><dd>eCTD v3.2.2 → eCTD v4.0</dd></div><div><dt>Standards snapshot</dt><dd>fda-cder-demo-v1</dd></div><div><dt>Operation</dt><dd>identifier-based reuse</dd></div></dl>
            <label>Scenario<select value={scenario} onChange={(event) => setScenario(event.target.value as TargetContext["scenario_mode"])}><option value="prospective_forward_compatibility">Prospective forward compatibility</option><option value="current_operational">Current operational</option></select></label>
            <label>Metadata migration intent<select value={intent} onChange={(event) => setIntent(event.target.value as MetadataIntent)}><option value="preserve-existing-lifecycle">Preserve existing lifecycle</option><option value="normalize-metadata">Normalize metadata</option><option value="unspecified">Unspecified</option></select></label>
            <p className="field-note">Manufacturer partitioning: unknown (visible advisory input)</p>
          </fieldset>
          <label className="confirm-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/> I confirm this target context and that the upload is synthetic or de-identified.</label>
          <button className="primary-button" disabled={!file || !confirmed || busy || selectedProfile?.availability !== "available"}>{busy ? "Parsing…" : "Parse and analyze"}</button>
          {error && <p role="alert" className="error-copy">{error}</p>}
        </form>
        <section className="panel scope-panel" aria-labelledby="controlled-scope"><h2 id="controlled-scope">Controlled scope</h2><p>RegBridge accepts a bounded FDA/CDER eCTD v3.2.2 public-standards profile and validates its two XML backbones against pinned local DTDs. It does not perform complete FDA validation or assess submission readiness.</p><p>Demo preset: <code>data/demo-dossiers/m4-2/regbridge-m4-2-public-standards.zip</code>. Raw ZIP bytes are discarded after parsing.</p></section>
      </section>
      {inventory && (
        <section className="panel profile-results motion-enter">
          <h2>Controlled v3.2.2 profile checks</h2>
          <p className="result-lead"><CheckCircle aria-hidden="true"/> Supported profile checks {inventory.package_profile_status}</p>
          <dl className="context-list">
            <div><dt>Sequence root</dt><dd>{inventory.detected_sequence_root}</dd></div>
            <div><dt>Profile</dt><dd>{inventory.input_profile_id} · {inventory.input_profile_version}</dd></div>
            <div><dt>Documents</dt><dd>{inventory.leaves.length}</dd></div>
            <div><dt>Index MD5</dt><dd>{inventory.index_md5_matches ? "matched" : "not verified"}</dd></div>
            <div><dt>Warnings</dt><dd>{inventory.warnings.length}</dd></div>
            <div><dt>Policy coverage</dt><dd>{Object.entries(inventory.policy_coverage_counts).map(([name, count]) => `${name}: ${count}`).join(" · ") || "none"}</dd></div>
          </dl>
          <p><strong>DTD identities:</strong> {inventory.xml_declarations.map((item) => `${item.dtd_asset_id ?? "unidentified"} ${item.effective_dtd_version ?? "unknown"} (${item.dtd_validation_result})`).join(" · ")}</p>
          <ul>{inventory.profile_checks.map((check) => <li key={check.id}><strong>{check.label}: {check.status}</strong> — {check.detail}</li>)}</ul>
          {inventory.warnings.length > 0 && <ul>{inventory.warnings.map((warning) => <li key={`${warning.code}-${warning.locator}`}><strong>{warning.code}</strong> — {warning.message}</li>)}</ul>}
          <h3>Document policy coverage</h3>
          <ul>{inventory.leaves.map((leaf) => <li key={leaf.id}><strong>{leaf.title}: {leaf.policy_coverage_status}</strong> — {leaf.policy_coverage_basis}</li>)}</ul>
          {inventory.package_files.some((item) => item.member_type === "UNSUPPORTED") && <p><strong>Unsupported members:</strong> {inventory.package_files.filter((item) => item.member_type === "UNSUPPORTED").map((item) => item.path).join(", ")}. No reuse decision is assigned to these members.</p>}
        </section>
      )}
      {run && (
        <section className="results-stack motion-enter" aria-live="polite">
          <div className="panel">
            <p className="panel-kicker">Dossier analysis · {run.state}</p>
            <h2>Package summary</h2>
            {run.summary ? (
              <div className="summary-cards">
                <article><strong>{run.summary.analyzed_count}</strong><span>Analyzed</span></article>
                <article><strong>{run.summary.human_approval_count}</strong><span>Human approval</span></article>
                <article><strong>{run.summary.failed_count}</strong><span>Failed</span></article>
              </div>
            ) : (
              <p>Analysis is running…</p>
            )}
          </div>
          {run.results.map((item) => (
            <details
              className="panel leaf-result"
              key={item.leaf_id}
              open={openLeaf === item.leaf_id}
              onToggle={(event) => {
                const isOpen = event.currentTarget.open;
                setOpenLeaf((current) => (isOpen ? item.leaf_id : current === item.leaf_id ? null : current));
              }}
            >
              <summary className="leaf-heading">
                <span><Database aria-hidden="true"/><strong>{item.analysis.source_artifact.title}</strong></span>
                <span>{item.analysis.decision}</span>
              </summary>
              <div className="leaf-details">
                <p><strong>Severity:</strong> {item.analysis.severity} · <strong>Human approval:</strong> {item.analysis.human_approval_required ? "required" : "not required"}</p>
                <p>{item.analysis.rationale}</p>
                <h3>Repair or next action</h3>
                <code>{item.analysis.repair.type}</code>
                <p>{item.analysis.repair.description}</p>
                <h3>Findings and evidence</h3>
                {item.analysis.findings.map((finding) => <blockquote key={finding.id}>{finding.rationale}<cite>{finding.evidence_ids.join(", ")}</cite></blockquote>)}
                <h3>Model record</h3>
                <p>{item.model.model_profile_id} · {item.model.adapter_type} · {item.model.status} · {item.model.latency_ms.toFixed(1)} ms</p>
                <h3>Chronological trace</h3>
                <ol>{item.analysis.trace.map((step) => <li key={step.sequence}><strong>{step.component}</strong> — {step.summary}</li>)}</ol>
                <GraphNeighborhood graph={item.graph}/>
              </div>
            </details>
          ))}
        </section>
      )}
    </main>
  );
}
