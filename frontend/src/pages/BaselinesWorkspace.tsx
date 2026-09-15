import { defaultTarget, savedTarget } from "../api/targetSetup";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Upload } from "iconoir-react";
import { createComparison, getComparison, getActiveProductConfiguration, getProductDemoPackage, parseUpload } from "../api/client";
import type { ApplicationInventory, ComparisonCell, ComparisonRun } from "../api/contracts";
import { errorMessage, readable } from "../api/wording";
import { FlowLoading, WorkspaceFlow } from "../components/WorkspaceFlow";

import { ConfigurationDisclosure, ProductSetup } from "../components/ProductSetup";
import { DocumentReview } from "../components/ReviewWorkspace";
import { comparisonDocument } from "../api/presentation";

const systemNames: Record<string, string> = { B0: "B0 · Document agent", B1: "B1 · Retrieval agent", B2: "B2 · Rules only", RegBridge: "RegBridge" };

export function BaselinesWorkspace() {
  const models = useQuery({ queryKey: ["product-config"], queryFn: getActiveProductConfiguration });
  const [inventory, setInventory] = useState<ApplicationInventory | null>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("regbridge.inventory") ?? "null") as ApplicationInventory | null;
      return saved && typeof saved.id === "string" && Array.isArray(saved.leaves) ? saved : null;
    } catch { return null; }
  });
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string[]>(inventory?.leaves.map((leaf) => leaf.id) ?? []);
  const [context, setContext] = useState(() => savedTarget(inventory?.id));
  const [run, setRun] = useState<ComparisonRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "compare" | null>(null);
  const [presetBusy, setPresetBusy] = useState(false);
  const [choosingFile, setChoosingFile] = useState(!inventory);
  const terminal = run && ["completed", "partial_failed", "failed"].includes(run.state);
  const processing = Boolean(busy || (run && !terminal));
  const profile = models.data;
  useEffect(() => {
    if (!run || terminal || error) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void getComparison(run.comparison_id).then((next) => { if (active) setRun(next); }).catch((cause: unknown) => { if (active) setError(errorMessage(cause)); });
    }, 700);
    return () => { active = false; window.clearTimeout(timer); };
  }, [run, terminal, error]);
  const grouped = useMemo(() => (run?.results ?? []).reduce<Record<string, ComparisonCell[]>>((result, item) => {
    (result[item.leaf_id] ??= []).push(item); return result;
  }, {}), [run]);

  async function upload() {
    if (!file || busy) return;
    setBusy("upload"); setError(null);
    try {
      const parsed = await parseUpload(file);
      setInventory(parsed); setContext(defaultTarget()); setSelected(parsed.leaves.map((leaf) => leaf.id)); setFile(null); setChoosingFile(false);
      sessionStorage.setItem("regbridge.inventory", JSON.stringify(parsed));
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); }
  }
  async function compare() {
    if (!inventory || !selected.length || busy || profile?.availability !== "available" || file) return;
    setBusy("compare"); setError(null); setRun(null);
    try { setRun(await createComparison(inventory.id, context, selected)); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); }
  }

  return <WorkspaceFlow step={processing ? "loading" : terminal ? "results" : choosingFile ? "setup" : "options"}
    title={processing ? busy === "upload" ? "Reading your dossier" : "Comparing four approaches" : terminal ? "Your comparison results" : "Compare analysis approaches"}
    description={processing ? undefined : terminal ? "See where the systems agree, and explore the reasons behind each decision." : "Run the same documents through RegBridge and three alternative approaches."}
    onBack={terminal ? () => { setRun(null); setError(null); } : undefined}>
    {processing ? <FlowLoading label={busy === "upload" ? "Checking your package" : "Running the comparison"} detail={busy === "upload" ? "Reading the document list so you can choose what to compare." : "Each approach receives the same selected documents. Results will appear here when the run finishes."} error={error} onRetry={() => setError(null)}/> : !terminal && <div className="flow-form">
      <section className="panel upload-panel">
        {choosingFile ? <>
        <h2><Upload aria-hidden="true"/> Choose your dossier</h2>
        <p>{inventory ? `${inventory.leaves.length} documents are available from your last upload.` : "Use a public, synthetic, or de-identified FDA/CDER eCTD v3.2.2 ZIP containing one sequence."}</p>
        <button type="button" disabled={presetBusy} onClick={() => { setPresetBusy(true); setError(null); void getProductDemoPackage().then(setFile).catch((cause: unknown) => setError(errorMessage(cause))).finally(() => setPresetBusy(false)); }}>{presetBusy ? "Loading sample..." : "Try a sample dossier"}</button>
        <label>Dossier ZIP<input aria-label="Comparison dossier ZIP" type="file" accept=".zip,application/zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)}/></label>
        {file && <p className="field-note">Selected: {file.name}. Read this package before comparing.</p>}
        <button onClick={() => void upload()} disabled={!file}>Read document list</button>
        {inventory && <button onClick={() => { setFile(null); setChoosingFile(false); }}>Keep the previous dossier</button>}
        </> : <div className="selected-dossier"><p>{inventory?.leaves.length} documents are available from your last upload.</p><button onClick={() => setChoosingFile(true)}>Change dossier</button></div>}
        {!choosingFile && <>
        {inventory && <fieldset><legend>Choose documents to compare</legend>
          {inventory.leaves.map((leaf) => <label className="confirm-row" key={leaf.id}><input type="checkbox" checked={selected.includes(leaf.id)} onChange={() => setSelected((current) => current.includes(leaf.id) ? current.filter((id) => id !== leaf.id) : [...current, leaf.id])}/><span>{leaf.title}<small>{readable(leaf.policy_coverage_status)}</small></span></label>)}
          {!selected.length && <p className="field-note">Select at least one document to continue.</p>}
        </fieldset>}
        {models.isPending && <p role="status">Loading analysis configuration...</p>}
        {models.isError && <div role="alert"><p>Analysis configuration is unavailable.</p><button onClick={() => void models.refetch()}>Reload configuration</button></div>}
        {profile && <ConfigurationDisclosure config={profile}/>}
        <ProductSetup value={context} onChange={setContext}/>
        <details><summary>What will be compared?</summary><p>B0 reads documents directly. B1 retrieves relevant evidence. B2 checks encoded rules without semantic inspection. RegBridge combines rules, a regulatory graph, and document inspection. B0, B1, and RegBridge use the same server configuration and selected target context.</p></details>
        <button className="primary-button" onClick={() => void compare()} disabled={!inventory || !selected.length || Boolean(file) || profile?.availability !== "available"}>Run comparison</button>
        </>}
        {error && <p role="alert" className="error-copy">{error}</p>}
      </section>
      <p className="field-note">This comparison shows different decisions, not which system is correct. It does not score accuracy or rank the approaches.</p>
    </div>}
    {run && terminal && <section className="results-stack motion-enter">
      <div className="panel"><h2>{readable(run.state)}</h2><p>This is a comparison of your selected documents, not a benchmark evaluation. Agreement does not establish that a decision is correct.</p>{run.state !== "completed" && <p>Some system runs could not finish. Their missing decisions are shown separately from completed results. Return to setup to try again.</p>}</div>
      {Object.entries(grouped).map(([leafId, cells]) => <article className="panel" key={leafId}>
        <h2>{inventory?.leaves.find((leaf) => leaf.id === leafId)?.title ?? "Document"}</h2>
        <p>{readable(inventory?.leaves.find((leaf) => leaf.id === leafId)?.policy_coverage_status)}</p>
        <div className="table-scroll" role="region" aria-label={`${inventory?.leaves.find((leaf) => leaf.id === leafId)?.title ?? leafId} system comparison`} tabIndex={0}><table className="metrics-table"><thead><tr><th>Approach</th><th>Decision</th><th>Severity</th><th>Next action</th><th>Human review</th><th>Evidence cited</th><th>Status</th><th>Time</th></tr></thead><tbody>{cells.map((cell) => <tr key={cell.system}>
          <th>{systemNames[cell.system] ?? cell.system}</th><td>{cell.status !== "completed" ? "No decision issued" : readable(cell.decision)}</td><td>{readable(cell.severity)}</td><td>{readable(cell.action)}</td><td>{cell.human_review_required == null ? "Not assessed" : cell.human_review_required ? "Required" : "Not required"}</td><td>{cell.evidence_ids.length}</td><td>{readable(cell.status)}</td><td>{(cell.model.latency_ms / 1000).toFixed(1)} s</td>
        </tr>)}</tbody></table></div>
        {cells.map((cell) => <details key={`${cell.system}-details`}><summary>{systemNames[cell.system] ?? cell.system}: explanation and evidence</summary>
          {inventory?.leaves.find(l => l.id === cell.leaf_id) && <DocumentReview document={comparisonDocument(inventory.leaves.find(l => l.id === cell.leaf_id)!, cell)}/>}
        </details>)}
      </article>)}
      {run.failures.map((failure, index) => <section className="panel" key={`${failure.leaf_id}-${index}`}><h2>Comparison could not finish</h2><p>{inventory?.leaves.find((leaf) => leaf.id === failure.leaf_id)?.title ?? "Document"}</p><p>{inventory?.leaves.find((leaf) => leaf.id === failure.leaf_id)?.href}</p><p>No decision was issued for this failed step. Return to setup to try again.</p><details><summary>Technical error details</summary><pre>{JSON.stringify(failure, null, 2)}</pre></details></section>)}
    </section>}
  </WorkspaceFlow>;
}
