import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Upload } from "iconoir-react";
import { createComparison, getComparison, getModels, getProductDemoPackage, parseUpload } from "../api/client";
import type { ApplicationInventory, ComparisonCell, ComparisonRun, TargetContext } from "../api/contracts";
import { errorMessage, readable } from "../api/wording";
import { FlowLoading, WorkspaceFlow } from "../components/WorkspaceFlow";

function target(): TargetContext { return { authority: "FDA", center: "CDER", application_type: "NDA", source_standard: "eCTD-3.2.2", target_standard: "eCTD-4.0", analysis_date: new Date().toISOString().slice(0, 10), reuse_operation: "reference-existing-content", standards_snapshot_id: "fda-cder-demo-v1", scenario_mode: "prospective_forward_compatibility", metadata_plan: { intent: "preserve-existing-lifecycle", manufacturer_partitioning: "unknown", replacement_manufacturer_value: null } }; }
const systemNames: Record<string, string> = { B0: "B0 · Document agent", B1: "B1 · Retrieval agent", B2: "B2 · Rules only", RegBridge: "RegBridge" };

export function BaselinesWorkspace() {
  const models = useQuery({ queryKey: ["models"], queryFn: getModels });
  const [inventory, setInventory] = useState<ApplicationInventory | null>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("regbridge.inventory") ?? "null") as ApplicationInventory | null;
      return saved && typeof saved.id === "string" && Array.isArray(saved.leaves) ? saved : null;
    } catch { return null; }
  });
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string[]>(inventory?.leaves.map((leaf) => leaf.id) ?? []);
  const [modelId, setModelId] = useState("gpt-5.5");
  const [run, setRun] = useState<ComparisonRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "compare" | null>(null);
  const [presetBusy, setPresetBusy] = useState(false);
  const [choosingFile, setChoosingFile] = useState(!inventory);
  const terminal = run && ["completed", "partial_failed", "failed"].includes(run.state);
  const processing = Boolean(busy || (run && !terminal));
  const profile = models.data?.models.find((item) => item.model_id === modelId);
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
      setInventory(parsed); setSelected(parsed.leaves.map((leaf) => leaf.id)); setFile(null); setChoosingFile(false);
      sessionStorage.setItem("regbridge.inventory", JSON.stringify(parsed));
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(null); }
  }
  async function compare() {
    if (!inventory || !selected.length || busy || profile?.availability !== "available" || file) return;
    setBusy("compare"); setError(null); setRun(null);
    try { setRun(await createComparison(inventory.id, modelId, target(), selected)); }
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
        <label>Analysis model<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.data?.models.map((item) => <option value={item.model_id} key={item.model_id} disabled={item.availability !== "available"}>{item.display_name}</option>)}</select></label>
        {models.isPending && <p role="status">Loading available models...</p>}
        {models.isError && <div role="alert"><p>We couldn't load the analysis models. Check that the local service is running.</p><button onClick={() => void models.refetch()}>Reload models</button></div>}
        {profile && <p className="field-note">{profile.execution_mode === "fixture" ? "Offline demonstration using repeatable sample responses." : profile.network_required ? "Document evidence is sent to the configured model provider." : "Analysis runs locally."} The selected model is shared by B0, B1, and RegBridge. B2 checks rules without AI.</p>}
        <details><summary>What will be compared?</summary><p>B0 reads documents directly. B1 retrieves relevant evidence. B2 checks encoded rules. RegBridge combines rules, a regulatory graph, and document inspection.</p><p>All four use the same FDA/CDER NDA context, prospective eCTD v4.0 scenario, and intent to keep the existing lifecycle. B0 and B1 receive the same complete set of repair actions.</p></details>
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
          <p>{cell.rationale || "This system did not return a completed explanation."}</p>
          {cell.status !== "completed" && <p>The system could not complete this document. No regulatory decision was issued. Return to setup to try again.</p>}
          <p><strong>Evidence:</strong> {cell.evidence_ids.join(", ") || "None cited"}</p><p><strong>Rules:</strong> {cell.rule_ids.join(", ") || "None triggered"}</p>
          <details><summary>Technical record</summary><p>Decision: {cell.decision ?? "none"} · Action: {cell.action ?? "none"} · Status: {cell.status}</p>
            {cell.model.status_detail && <p>{cell.model.status_detail}</p>}{cell.failure && <p>{cell.failure}</p>}{cell.model.failure && <p>{cell.model.failure}</p>}
            <ol>{cell.trace.map((entry, index) => <li key={index}><pre>{JSON.stringify(entry, null, 2)}</pre></li>)}</ol>
            {cell.system === "B1" && <ol>{cell.retrieval.map((hit) => <li key={hit.alias}>{hit.alias}: {hit.evidence_id} ({hit.score.toFixed(3)})</li>)}</ol>}
            {cell.graph && <p>Graph: {cell.graph.nodes.length} nodes / {cell.graph.edges.length} edges. Full graph records are available in the result API.</p>}
          </details>
        </details>)}
      </article>)}
      {run.failures.map((failure, index) => <section className="panel" key={`${failure.leaf_id}-${index}`}><h2>Comparison could not finish</h2><p>{inventory?.leaves.find((leaf) => leaf.id === failure.leaf_id)?.title ?? "Document"}</p><p>No decision was issued for this failed step. Return to setup to try again.</p><details><summary>Technical error details</summary><p>{failure.stage}: {failure.cause}</p></details></section>)}
    </section>}
  </WorkspaceFlow>;
}
