import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Upload } from "iconoir-react";

import { createDossierAnalysis, getDossierAnalysis, getModels, getProductDemoPackage, parseUpload } from "../api/client";
import type { ApplicationInventory, DossierAnalysisRun, MetadataIntent, TargetContext } from "../api/contracts";
import { GraphNeighborhood } from "../components/GraphNeighborhood";
import { FlowLoading, WorkspaceFlow } from "../components/WorkspaceFlow";
import { errorMessage, readable } from "../api/wording";

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
  const [presetBusy, setPresetBusy] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const terminal = run && ["completed", "partial_failed", "failed"].includes(run.state);

  useEffect(() => {
    if (!run || terminal || error) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void getDossierAnalysis(run.run_id).then((next) => { if (active) setRun(next); }).catch((cause: unknown) => { if (active) setError(errorMessage(cause)); });
    }, 700);
    return () => { active = false; window.clearTimeout(timer); };
  }, [run, terminal, error]);

  const selectedProfile = useMemo(
    () => models.data?.models?.find((item) => item.model_id === modelId),
    [models.data, modelId],
  );

  async function submit() {
    if (!file || !confirmed || busy || selectedProfile?.availability !== "available") return;
    setBusy(true); setError(null); setRun(null); setInventory(null); setOpenLeaf(null);
    try {
      const parsed = await parseUpload(file);
      setInventory(parsed);
      sessionStorage.setItem("regbridge.inventory", JSON.stringify(parsed));
      const created = await createDossierAnalysis(parsed.id, modelId, target(intent, scenario));
      setRun(created);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  const processing = busy || Boolean(run && !terminal);
  const step = processing ? "loading" : terminal ? "results" : optionsOpen ? "options" : "setup";
  return (
    <WorkspaceFlow step={step} title={processing ? "Reviewing your dossier" : terminal ? "Your dossier results" : "Analyze a dossier"}
      description={processing ? undefined : terminal ? "Review each document's decision and what to do next." : "Upload your dossier, choose how to reuse its content, and review the risks."}
      onBack={terminal ? () => { setRun(null); setInventory(null); setError(null); } : undefined}>
      {processing ? <FlowLoading label={busy ? "Checking your package" : "Analyzing your documents"} detail={busy ? "Reading the ZIP and checking its structure." : "Checking placement, metadata, and document content. Results will appear here when the run finishes."} error={error} onRetry={() => setError(null)}/> : !terminal && <section className="flow-form">
        <form className="panel upload-panel" onSubmit={(event) => { event.preventDefault(); if (optionsOpen) void submit(); else if (file) setOptionsOpen(true); }}>
          {!optionsOpen ? <>
          <h2><Upload aria-hidden="true"/> Choose your dossier</h2>
          <p>Use a public, synthetic, or de-identified FDA/CDER eCTD v3.2.2 ZIP containing one sequence.</p>
          <button type="button" disabled={presetBusy} onClick={() => { setPresetBusy(true); setError(null); void getProductDemoPackage().then(setFile).catch((cause: unknown) => setError(errorMessage(cause))).finally(() => setPresetBusy(false)); }}>{presetBusy ? "Loading sample..." : "Try a sample dossier"}</button>
          {file && <p className="field-note">Selected: {file.name}</p>}
          <label>Dossier ZIP<input aria-label="Dossier ZIP" type="file" accept=".zip,application/zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
          <button className="primary-button" disabled={!file || presetBusy}>Continue to options</button>
          </> : <>
          <div className="selected-dossier"><p>Selected: {file?.name}</p><button type="button" onClick={() => setOptionsOpen(false)}>Change dossier</button></div>
          <label>Analysis model<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.data?.models.map((profile) => <option key={profile.model_id} value={profile.model_id} disabled={profile.availability !== "available"}>{profile.display_name}{profile.availability !== "available" ? " (unavailable)" : ""}</option>)}</select></label>
          {models.isPending && <p role="status">Loading available models...</p>}
          {models.isError && <div role="alert"><p>We couldn't load the analysis models. Check that the local service is running.</p><button type="button" onClick={() => void models.refetch()}>Reload models</button></div>}
          {selectedProfile && <p className="field-note">{selectedProfile.execution_mode === "fixture" ? "Offline demonstration: uses repeatable sample responses, without a live AI call." : selectedProfile.network_required ? "Online analysis: document evidence is sent to the configured model provider." : "Analysis runs locally without a network connection."}</p>}
          <fieldset><legend>Choose your options</legend><p className="field-note">FDA / CDER · NDA · eCTD v3.2.2 to v4.0 · Reuse existing content by reference</p>
            <label>Scenario<select value={scenario} onChange={(event) => setScenario(event.target.value as TargetContext["scenario_mode"])}><option value="prospective_forward_compatibility">Prospective forward compatibility</option><option value="current_operational">Current operational</option></select></label>
            {scenario === "current_operational" && <p className="field-note">FDA forward compatibility is currently unavailable. This mode reports that limitation without running prospective compatibility rules or AI inspection.</p>}
            <label>How should metadata be handled?<select value={intent} onChange={(event) => setIntent(event.target.value as MetadataIntent)}><option value="preserve-existing-lifecycle">Keep the existing lifecycle</option><option value="normalize-metadata">Standardize metadata for the new context</option><option value="unspecified">I'm not sure yet</option></select></label>
            <p className="field-note">Manufacturer grouping is unknown. The analysis will retain any related uncertainty.</p>
          </fieldset>
          <label className="confirm-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/> I confirm this target context and that the upload is synthetic or de-identified.</label>
          <button className="primary-button" disabled={!file || !confirmed || busy || selectedProfile?.availability !== "available"}>
            Parse and analyze
          </button>
          </>}
          {error && <p role="alert" className="error-copy">{error}</p>}
        </form>
        <p className="field-note">The uploaded ZIP is discarded after parsing. Only supported package checks and document risks are assessed.</p>
      </section>}
      {inventory && terminal && (
        <details className="panel profile-results motion-enter">
          <summary>Package checks and document coverage</summary>
          <p className="result-lead">Package checks: {readable(inventory.package_profile_status)}</p>
          <dl className="context-list">
            <div><dt>Sequence root</dt><dd>{inventory.detected_sequence_root}</dd></div>
            <div><dt>Profile</dt><dd>{inventory.input_profile_id} · {inventory.input_profile_version}</dd></div>
            <div><dt>Documents</dt><dd>{inventory.leaves.length}</dd></div>
            <div><dt>Index MD5</dt><dd>{inventory.index_md5_matches ? "matched" : "not verified"}</dd></div>
            <div><dt>Warnings</dt><dd>{inventory.warnings.length}</dd></div>
            <div><dt>Policy coverage</dt><dd>{Object.entries(inventory.policy_coverage_counts).map(([name, count]) => `${readable(name)}: ${count}`).join(" · ") || "none"}</dd></div>
          </dl>
          <p><strong>DTD identities:</strong> {inventory.xml_declarations.map((item) => `${item.dtd_asset_id ?? "unidentified"} ${item.effective_dtd_version ?? "unknown"} (${item.dtd_validation_result})`).join(" · ")}</p>
          <ul>{inventory.profile_checks.map((check) => <li key={check.id}><strong>{check.label}: {check.status}</strong> — {check.detail}</li>)}</ul>
          {inventory.warnings.length > 0 && <ul>{inventory.warnings.map((warning) => <li key={`${warning.code}-${warning.locator}`}><strong>{readable(warning.code)}</strong> — {warning.message}</li>)}</ul>}
          <h3>Document policy coverage</h3>
          <ul>{inventory.leaves.map((leaf) => <li key={leaf.id}><strong>{leaf.title}: {readable(leaf.policy_coverage_status)}</strong> — {leaf.policy_coverage_basis}</li>)}</ul>
          {inventory.package_files.some((item) => item.member_type === "UNSUPPORTED") && <p><strong>Unsupported members:</strong> {inventory.package_files.filter((item) => item.member_type === "UNSUPPORTED").map((item) => item.path).join(", ")}. No reuse decision is assigned to these members.</p>}
        </details>
      )}
      {run && terminal && (
        <section className="results-stack motion-enter" aria-live="polite">
          <div className="panel">
            <p className="panel-kicker">Dossier analysis · {readable(run.state)}</p>
            <h2>Package summary</h2>
            {run.summary ? (
              <div className="summary-cards">
                <article><strong>{run.summary.analyzed_count}</strong><span>Successfully analyzed</span></article>
                <article><strong>{run.summary.human_approval_count}</strong><span>Human approval required</span></article>
                <article><strong>{run.summary.model_abstention_count}</strong><span>Inspections needing more evidence</span></article>
                <article><strong>{run.summary.pipeline_failure_count}</strong><span>Documents that could not be analyzed</span></article>
              </div>
            ) : (
              <p>The run has finished. Review the available results and any failures below.</p>
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
                <span>{readable(item.analysis.decision)}</span>
              </summary>
              <div className="leaf-details">
                <p><strong>Severity:</strong> {item.analysis.severity} · <strong>Human approval:</strong> {item.analysis.human_approval_required ? "required" : "not required"}</p>
                <p>{item.analysis.rationale}</p>
                <h3>Repair or next action</h3>
                <strong>{readable(item.analysis.repair.type)}</strong>
                <p>{item.analysis.repair.description}</p>
                <h3>Findings and evidence</h3>
                {item.analysis.findings.map((finding) => <blockquote key={finding.id}>{finding.rationale}<cite>{finding.evidence_ids.join(", ")}</cite></blockquote>)}
                {item.analysis.evidence?.map((evidence) => <blockquote key={evidence.id}><p>{evidence.text}</p><cite>{evidence.locator} · {"source_id" in evidence ? evidence.source_id : "Uploaded document"}</cite></blockquote>)}
                <h3>Document inspection</h3>
                <p>{readable(item.model.status)}</p>
                {item.model.status === "abstained" && <p>The model could not reach a conclusion from the available evidence. This does not mean stale content was found. Any required structural changes still apply.</p>}
                {item.analysis.unresolved_uncertainty?.length > 0 && <ul>{item.analysis.unresolved_uncertainty.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
                {typeof item.analysis.confidence === "number" && <p>Reported confidence: {Math.round(item.analysis.confidence * 100)}%. This is not a probability of FDA acceptance.</p>}
                <details><summary>Technical analysis record</summary>
                <dl className="context-list">
                  <div><dt>Model profile</dt><dd>{item.model.model_profile_id}</dd></div>
                  <div><dt>Actual adapter</dt><dd>{item.model.adapter_type}</dd></div>
                  <div><dt>Execution mode</dt><dd>{item.model.execution_mode}</dd></div>
                  <div><dt>Status</dt><dd>{item.model.status}</dd></div>
                  <div><dt>Attempts</dt><dd>{item.model.attempt_count}</dd></div>
                  <div><dt>Decision basis</dt><dd>{item.analysis.decision_basis.replaceAll("_", " ")}</dd></div>
                </dl>
                {item.model.status_detail && <p><strong>Model status detail:</strong> {item.model.status_detail}</p>}
                {item.model.reason_category && <p><strong>Reason category:</strong> {item.model.reason_category}</p>}
                {item.model.failure && <p><strong>Failure category:</strong> {item.model.failure}</p>}
                <p>Decision code: <code>{item.analysis.decision}</code> · Action code: <code>{item.analysis.repair.type}</code></p>
                <h3>Chronological trace</h3>
                <ol>{item.analysis.trace.map((step) => <li key={step.sequence}><strong>{step.component}</strong> — {step.summary}</li>)}</ol>
                </details>
                <GraphNeighborhood graph={item.graph}/>
              </div>
            </details>
          ))}
          {run.failures.map((failure) => <section className="panel" key={failure.leaf_id}><h2>Document could not be analyzed</h2><p><strong>{inventory?.leaves.find((leaf) => leaf.id === failure.leaf_id)?.title ?? "Document"}</strong></p><p>The analysis could not finish, so no reuse decision was issued. Return to setup to try again. If this continues, share the technical details with the person running the service.</p><details><summary>Technical error details</summary><p>{failure.leaf_id} · {failure.failure_category} · {failure.stage}</p></details></section>)}
        </section>
      )}
    </WorkspaceFlow>
  );
}
