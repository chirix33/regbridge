import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Database, Upload, WarningTriangle } from "iconoir-react";

import { createDossierAnalysis, getDossierAnalysis, getModels, parseUpload } from "../api/client";
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
        <aside className="panel"><h2>Controlled scope</h2><p>RegBridge securely parses and validates a controlled FDA eCTD v3.2.2 package profile for supported structural, lifecycle, metadata, checksum, and document-evidence predicates. It does not perform complete FDA submission validation.</p><p>Raw ZIP bytes are discarded after parsing. Inventories are local, capacity bounded, expire, and do not survive a server restart.</p></aside>
      </section>
      {inventory && <section className="panel profile-results"><h2>Controlled v3.2.2 profile checks</h2><p className="result-lead"><CheckCircle aria-hidden="true"/> Supported profile checks {inventory.package_profile_status}</p><dl className="context-list"><div><dt>Sequence root</dt><dd>{inventory.detected_sequence_root}</dd></div><div><dt>Profile</dt><dd>{inventory.input_profile_id}</dd></div><div><dt>Documents</dt><dd>{inventory.leaves.length}</dd></div><div><dt>Index MD5</dt><dd>{inventory.index_md5_matches ? "matched" : "not verified"}</dd></div></dl><ul>{inventory.profile_checks.map((check) => <li key={check.id}><strong>{check.label}: {check.status}</strong> — {check.detail}</li>)}</ul></section>}
      {run && <section className="results-stack" aria-live="polite"><div className="panel"><p className="panel-kicker">Dossier analysis · {run.state}</p><h2>Package summary</h2>{run.summary ? <div className="summary-cards"><article><strong>{run.summary.analyzed_count}</strong><span>Analyzed</span></article><article><strong>{run.summary.human_approval_count}</strong><span>Human approval</span></article><article><strong>{run.summary.failed_count}</strong><span>Failed</span></article></div> : <p>Analysis is running…</p>}</div>{run.results.map((item) => <article className="panel leaf-result" key={item.leaf_id}><button className="leaf-heading" onClick={() => setOpenLeaf(openLeaf === item.leaf_id ? null : item.leaf_id)} aria-expanded={openLeaf === item.leaf_id}><span><Database aria-hidden="true"/><strong>{item.analysis.source_artifact.title}</strong></span><span>{item.analysis.decision}</span></button>{openLeaf === item.leaf_id && <div className="leaf-details"><p><strong>Severity:</strong> {item.analysis.severity} · <strong>Human approval:</strong> {item.analysis.human_approval_required ? "required" : "not required"}</p><p>{item.analysis.rationale}</p><h3>Repair or next action</h3><code>{item.analysis.repair.type}</code><p>{item.analysis.repair.description}</p><h3>Findings and evidence</h3>{item.analysis.findings.map((finding) => <blockquote key={finding.id}>{finding.rationale}<cite>{finding.evidence_ids.join(", ")}</cite></blockquote>)}<h3>Model record</h3><p>{item.model.model_profile_id} · {item.model.adapter_type} · {item.model.status} · {item.model.latency_ms.toFixed(1)} ms</p><h3>Chronological trace</h3><ol>{item.analysis.trace.map((step) => <li key={step.sequence}><strong>{step.component}</strong> — {step.summary}</li>)}</ol><GraphNeighborhood graph={item.graph}/></div>}</article>)}</section>}
    </main>
  );
}
