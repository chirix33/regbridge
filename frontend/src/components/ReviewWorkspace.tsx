import { useEffect, useRef, useState } from "react";
import type { ReviewDocument } from "../api/presentation";
import { documentReviewItems, groupReviewItems, nextStep, statusLabel } from "../api/presentation";
import { readable } from "../api/wording";
import { GraphNeighborhood } from "./GraphNeighborhood";

export function DocumentReview({ document: d }: { document: ReviewDocument }) {
  const explanation = d.explanation;
  return <article className="document-review">
    <header><h3>{d.leaf.title}</h3><p className="document-filename">{d.leaf.href}</p><p>Source section {d.leaf.heading} · {d.leaf.source_locator}</p></header>
    <p className="review-status">{d.statuses.map(statusLabel).join(" · ")}</p>
    <dl className="review-steps">
      <div><dt>Current</dt><dd>eCTD v3.2.2 section {d.leaf.heading}; recorded lifecycle operation: {d.leaf.operation}.
        {d.leaf.keywords.map(k => <span key={`${k.name}-${k.source_locator}`}> {k.name}: {k.raw_value}.</span>)}</dd></div>
      <div><dt>Recommended</dt><dd>{d.decision ? `Proposed document recommendation: ${readable(d.decision)}.` : "No regulatory decision issued."}</dd></div>
      <div><dt>Why</dt><dd>{d.rationale}</dd></div>
      <div><dt>Next step</dt><dd>{nextStep(d)}</dd></div>
    </dl>
    <p><strong>Human approval:</strong> {d.approval == null ? "Not assessed" : d.approval ? "Required before acting on the recommendation" : "Not required by the recorded result"}. No document edits or migration have been performed.</p>
    {!!documentReviewItems(d).length && <section aria-label={`Review items for ${d.leaf.title} (${d.system ?? "RegBridge"}, ${d.leaf.id})`}><h4>Review items for this document</h4><ul className="document-review-items">{documentReviewItems(d).map(item => <li key={item.id}><strong>{item.area}</strong><p>{item.found}</p><p>Next step: {item.next}</p></li>)}</ul></section>}
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
  const origin = useRef<HTMLButtonElement | null>(null);
  const leaves = [...new Map(documents.map(d => [d.leaf.id, d])).values()];
  const items = groupReviewItems(leaves);
  const activeItem = attentionOnly ? items.find(item => item.key === open) : null;
  const activeDocuments = attentionOnly ? activeItem?.documents : leaves.filter(d => d.leaf.id === open);
  const affected = new Set(items.flatMap(item => item.documents.map(d => d.leaf.id))).size;
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (open) heading.current?.focus(); }, [open]);
  const toggle = (key: string, button: HTMLButtonElement) => { origin.current = button; setOpen(open === key ? null : key); };
  return <section className="panel action-workspace">
    <h2>{attentionOnly ? "Review actions" : "Document inventory"}</h2>
    <div className="review-filters" aria-label="Document view"><button aria-pressed={attentionOnly} onClick={() => { setAttentionOnly(true); setOpen(null); }}>Needs attention</button><button aria-pressed={!attentionOnly} onClick={() => { setAttentionOnly(false); setOpen(null); }}>All documents</button></div>
    <p>{attentionOnly ? `${items.length} review items · ${affected} affected document leaves` : `${leaves.length} document leaves · ${items.length} review items`}. Review items and statuses may overlap. Separate leaves retain their own context even when they reference the same file.</p>
    {attentionOnly ? <>
      {!items.length && <p>No documents need attention in the recorded results. Open All documents to inspect the evaluated scope.</p>}
      <div className="action-overview" role="table" aria-label="Action overview"><div className="action-row action-head" role="row">{["Area", "What was found", "Next step", "Documents", "Status"].map(h => <span role="columnheader" key={h}>{h}</span>)}</div>
        {items.map((item, i) => <div className="action-row" role="row" key={item.key}>
          <div role="cell" data-label="Area"><button aria-describedby={`review-summary-${i}`} aria-expanded={open === item.key} onClick={e => toggle(item.key, e.currentTarget)}>{item.area}</button></div>
          <div role="cell" id={`review-summary-${i}`} data-label="What was found">{item.found}</div>
          <div role="cell" data-label="Next step">{item.next}</div>
          <div role="cell" data-label="Documents">{item.documents.length} {item.documents.length === 1 ? "leaf" : "leaves"}</div>
          <div role="cell" data-label="Status"><ul className="review-status-list">{item.statuses.map(s => <li key={s}>{statusLabel(s)}</li>)}</ul></div>
        </div>)}
      </div>
    </> : <div className="document-inventory" role="table" aria-label="Document inventory">
      <div className="inventory-row action-head" role="row">{["Document", "Filename", "Source section", "Assessment status", "Review items"].map(h => <span role="columnheader" key={h}>{h}</span>)}</div>
      {leaves.map(d => <div className="inventory-row" role="row" key={d.leaf.id}>
        <div role="cell" data-label="Document"><button aria-expanded={open === d.leaf.id} onClick={e => toggle(d.leaf.id, e.currentTarget)}>{d.leaf.title}</button><small>Leaf ID: {d.leaf.id}</small></div>
        <div role="cell" data-label="Filename">{d.leaf.href}</div>
        <div role="cell" data-label="Source section">{d.leaf.heading}</div>
        <div role="cell" data-label="Assessment status"><ul className="review-status-list">{d.statuses.map(s => <li key={s}>{statusLabel(s)}</li>)}</ul></div>
        <div role="cell" data-label="Review items">{documentReviewItems(d).length} {documentReviewItems(d).length === 1 ? "review item" : "review items"}</div>
      </div>)}
    </div>}
    {!!activeDocuments?.length && <section className="action-detail" aria-label="Affected document review"><h2 ref={heading} tabIndex={-1}>{attentionOnly ? activeItem?.area : "Document review"}</h2>{activeDocuments.map(d => <DocumentReview key={d.leaf.id} document={d}/>)}<button onClick={() => { setOpen(null); origin.current?.focus(); }}>Close document review</button></section>}
  </section>;
}
