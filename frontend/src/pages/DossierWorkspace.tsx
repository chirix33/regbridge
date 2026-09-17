import { defaultTarget } from "../api/targetSetup";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DossierPicker } from "../components/DossierPicker";

import { createDossierAnalysis, getDossierAnalysis, getActiveProductConfiguration, parseUpload } from "../api/client";
import type { ApplicationInventory, DossierAnalysisRun } from "../api/contracts";
import { ReviewWorkspace } from "../components/ReviewWorkspace";
import { dossierDocuments } from "../api/presentation";
import { ConfigurationDisclosure, ProductSetup } from "../components/ProductSetup";
import { FlowLoading, WorkspaceFlow } from "../components/WorkspaceFlow";
import { errorMessage, readable } from "../api/wording";

export function DossierWorkspace() {
  const models = useQuery({ queryKey: ["product-config"], queryFn: getActiveProductConfiguration });
  const [file, setFile] = useState<File | null>(null);
  const [inventory, setInventory] = useState<ApplicationInventory | null>(null);
  const [run, setRun] = useState<DossierAnalysisRun | null>(null);
  const [context, setContext] = useState(defaultTarget);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const materialWarnings = inventory?.warnings.filter(w => w.code !== "index-dtd-version-inferred") ?? [];
  const terminal = run && ["completed", "partial_failed", "failed"].includes(run.state);

  useEffect(() => {
    if (!run || terminal || error) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void getDossierAnalysis(run.run_id).then((next) => { if (active) setRun(next); }).catch((cause: unknown) => { if (active) setError(errorMessage(cause)); });
    }, 700);
    return () => { active = false; window.clearTimeout(timer); };
  }, [run, terminal, error]);

  const selectedProfile = models.data;

  async function submit() {
    if (!file || !confirmed || busy || selectedProfile?.availability !== "available") return;
    setBusy(true); setError(null); setRun(null); setInventory(null);
    try {
      const parsed = await parseUpload(file);
      setInventory(parsed);
      sessionStorage.setItem("regbridge.inventory", JSON.stringify(parsed));
      sessionStorage.setItem("regbridge.target", JSON.stringify({ inventoryId: parsed.id, context }));
      const created = await createDossierAnalysis(parsed.id, context);
      setRun(created);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  const processing = busy || Boolean(run && !terminal);
  const step = processing ? "loading" : terminal ? "results" : optionsOpen ? "options" : "setup";
  return (
    <WorkspaceFlow step={step} title={processing ? "Reviewing your dossier" : terminal ? "Your dossier results" : optionsOpen ? "Choose your review options" : "Choose your dossier"}
      description={processing ? undefined : terminal ? "Review each document's decision and what to do next." : undefined}
      onBack={terminal ? () => { setRun(null); setInventory(null); setError(null); } : undefined}>
      {processing ? <FlowLoading label={busy ? "Checking your package" : "Analyzing your documents"} detail={busy ? "Reading the ZIP and checking its structure." : "Checking placement, metadata, and document content. Results will appear here when the run finishes."} error={error} onRetry={() => setError(null)}/> : !terminal && <section className="flow-form">
        <form className="panel upload-panel" onSubmit={(event) => { event.preventDefault(); if (optionsOpen) void submit(); else if (file) setOptionsOpen(true); }}>
          {!optionsOpen ? <>
          <DossierPicker file={file} onChange={next => { setFile(next); setContext(defaultTarget()); setConfirmed(false); }}/>
          <button className="primary-button" disabled={!file}>Continue to options</button>
          </> : <>
          <div className="selected-dossier"><p>Selected: {file?.name}</p><button type="button" onClick={() => setOptionsOpen(false)}>Change dossier</button></div>
          {models.isPending && <p role="status">Loading analysis configuration...</p>}
          {models.isError && <div role="alert"><p>Analysis configuration is unavailable.</p><button type="button" onClick={() => void models.refetch()}>Reload configuration</button></div>}
          <ProductSetup value={context} onChange={setContext}/>
          <label className="confirm-row"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/> I confirm this target context and that the upload is synthetic or de-identified.</label>
          {selectedProfile && <ConfigurationDisclosure config={selectedProfile}/>}
          <button className="primary-button" disabled={!file || !confirmed || busy || selectedProfile?.availability !== "available"}>
            Parse and analyze
          </button>
          </>}
          {error && <p role="alert" className="error-copy">{error}</p>}
        </form>
      </section>}
      {inventory && terminal && (materialWarnings.length > 0 || ["failed", "unsupported"].includes(inventory.package_profile_status)) && <aside className="panel review-limitation" aria-label="Package limitations"><h2>Package limitations</h2><ul>{materialWarnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul><p>Package check status: {readable(inventory.package_profile_status)}. Review package details when interpreting document recommendations.</p></aside>}
      {run && terminal && inventory && <ReviewWorkspace documents={dossierDocuments(inventory, run)}/>}
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
    </WorkspaceFlow>
  );
}
