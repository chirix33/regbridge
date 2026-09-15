import { useEffect, useRef, useState } from "react";
import type { ReviewDocument } from "../api/presentation";
import { groupReviewItems, nextStep, overviewFinding } from "../api/presentation";
import { readable } from "../api/wording";
import { GraphNeighborhood } from "./GraphNeighborhood";

export function DocumentReview({ document: d }: { document: ReviewDocument }) {
  const explanation = d.explanation;
  return <article className="document-review">
    <header><h3>{d.leaf.title}</h3><p className="document-filename">{d.leaf.href}</p><p>Source section {d.leaf.heading} · {d.leaf.source_locator}</p></header>
    <p className="review-status">{d.statuses.join(" · ")}</p>
    <dl className="review-steps">
      <div><dt>Current</dt><dd>eCTD v3.2.2 section {d.leaf.heading}; recorded lifecycle operation: {d.leaf.operation}.
        {d.leaf.keywords.map(k => <span key={`${k.name}-${k.source_locator}`}> {k.name}: {k.raw_value}.</span>)}</dd></div>
      <div><dt>Recommended</dt><dd>{d.decision ? `Proposed document recommendation: ${readable(d.decision)}.` : "No regulatory decision issued."}</dd></div>
      <div><dt>Why</dt><dd>{d.rationale}</dd></div>
      <div><dt>Next step</dt><dd>{nextStep(d)}</dd></div>
    </dl>
    <p><strong>Human approval:</strong> {d.approval == null ? "Not assessed" : d.approval ? "Required before acting on the recommendation" : "Not required by the recorded result"}. No document edits or migration have been performed.</p>
    {d.statuses.includes("Incomplete inspection") && <p className="review-limitation"><strong>Inspection incomplete.</strong> Content inspection needs completion. This status does not mean stale content was found; any recorded structural recommendation still applies.</p>}
    {d.statuses.includes("Inspection intentionally omitted") && <p className="review-limitation">B2 intentionally checks rules without semantic inspection. This is neither an abstention nor content clearance.</p>}
    {d.statuses.includes("No change detected within evaluated checks") && <p>No change was detected within the selected FDA/CDER Module 3 checks and completed bounded inspection. This is not a full submission assessment.</p>}
    {(d.leaf.policy_coverage_status !== "EVALUATED_WITH_APPROVED_POLICY" || d.leaf.extraction_status !== "completed") && <p className="review-limitation">{d.leaf.policy_coverage_basis} Extraction: {d.leaf.extraction_status}.</p>}
    {!!explanation?.uncertainty?.length && <section><h4>Unresolved conditions</h4><ul>{explanation.uncertainty.map((u, i) => <li key={i}>{u}</li>)}</ul></section>}
    {d.limitation && <p>{d.limitation}</p>}
    {explanation?.limitations.map((l, i) => <p key={i} className="field-note">{l}</p>)}
    {!!explanation?.findings?.length && <section><h4>Recorded findings for this document</h4><p>The next step above is the overall document recommendation.</p><ul>{explanation.findings.map(f => <li key={f.id}><strong>{f.verification_basis === "semantic_inference" || f.enforcement_mode === "semantic_signal" ? "AI-assisted content finding" : "Standards-based check"}:</strong> {f.rationale}<small>Supporting evidence: {f.evidence_ids.join(", ")}</small></li>)}</ul></section>}
    <details className="review-disclosure"><summary>View supporting evidence</summary>
      {!explanation?.evidence.length && <p>No cited evidence passages are available in this record.</p>}
      {explanation?.evidence.map(e => {
        const source = explanation.sources.find(s => "source_id" in e && s.evidence_id === e.id && s.source_id === e.source_id && s.sha256 === e.source_sha256);
        return <figure key={e.id}><figcaption><strong>{"source_id" in e ? "Standards passage" : "Cited dossier excerpt"}</strong> · {e.id}</figcaption><blockquote>{e.text}</blockquote><p>{source ? `${source.title} · ${source.version}` : "source_id" in e ? "Verified source metadata unavailable" : d.leaf.title} · {e.locator}</p>{source && <a href={source.source_url} target="_blank" rel="noreferrer">Official source</a>}</figure>;
      })}
      <p>The standards-based checks are author-adjudicated research encodings. They have not been externally validated by a regulatory expert (expert_validated: false).</p>
    </details>
    <details className="review-disclosure"><summary>How {d.system ?? "RegBridge"} reached this result</summary>
      <p>Decision code: <code>{d.decision ?? "none"}</code> · Action code: <code>{d.action ?? "none"}</code></p>
      <p>Rule IDs: {d.ruleIds.join(", ") || "No rule reasoning supplied by this approach"}</p>
      <h4>Model execution record</h4><pre>{JSON.stringify(d.model, null, 2)}</pre>
      <h4>Trace</h4><pre>{JSON.stringify(d.trace, null, 2)}</pre>
      {d.graph ? <GraphNeighborhood graph={d.graph}/> : <p>No graph reasoning is supplied by this approach.</p>}
      <h4>Provenance and digests</h4><pre>{JSON.stringify({ file_sha256: d.leaf.file_sha256, evidence: explanation?.evidence ?? [], sources: explanation?.sources ?? [] }, null, 2)}</pre>
    </details>
  </article>;
}

export function ReviewWorkspace({ documents }: { documents: ReviewDocument[] }) {
  const [attentionOnly, setAttentionOnly] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const shown = documents.filter(d => !attentionOnly || d.attention);
  const items = groupReviewItems(shown);
  const affected = new Set(shown.map(d => d.leaf.href)).size;
  const active = items.find(item => item.key === open);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (open) heading.current?.focus(); }, [open]);
  return <section className="panel action-workspace">
    <h2>Review actions</h2>
    <div className="review-filters" aria-label="Document view"><button aria-pressed={attentionOnly} onClick={() => { setAttentionOnly(true); setOpen(null); }}>Needs attention</button><button aria-pressed={!attentionOnly} onClick={() => { setAttentionOnly(false); setOpen(null); }}>All documents</button></div>
    <p>{items.length} review items · {affected} unique {attentionOnly ? "affected documents" : "documents shown"}. Documents may appear in more than one review item or status.</p>
    {!items.length && <p>No documents need attention in the recorded results. Open All documents to inspect the evaluated scope.</p>}
    <div className="action-overview" role="table" aria-label="Action overview"><div className="action-row action-head" role="row">{["Area", "What was found", "Recommended next step", "Affected documents", "Status"].map(h => <span role="columnheader" key={h}>{h}</span>)}</div>
      {items.map((item, i) => { const d = item.documents[0]!; return <div className="action-row" role="row" key={item.key}>
        <div role="cell" data-label="Area"><button id={`review-action-${i}`} aria-describedby={`review-summary-${i}`} aria-expanded={open === item.key} onClick={() => setOpen(open === item.key ? null : item.key)}>{d.area}</button></div>
        <div role="cell" id={`review-summary-${i}`} data-label="What was found">{overviewFinding(d)}</div>
        <div role="cell" data-label="Recommended next step">{nextStep(d)}</div>
        <div role="cell" data-label="Affected documents">{new Set(item.documents.map(doc => doc.leaf.href)).size}</div>
        <div role="cell" data-label="Status">{d.statuses.join(" · ")}</div>
      </div>; })}
    </div>
    {active && <section className="action-detail" aria-label="Affected document review"><h2 ref={heading} tabIndex={-1}>{active.documents[0]!.area}</h2>{active.documents.map(d => <DocumentReview key={d.leaf.id} document={d}/>)}<button onClick={() => { const i = items.indexOf(active); setOpen(null); document.getElementById(`review-action-${i}`)?.focus(); }}>Close document review</button></section>}
  </section>;
}
