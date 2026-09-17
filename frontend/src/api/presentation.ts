import type { ApplicationInventory, ComparisonCell, DossierAnalysisRun, ModelExecutionRecord, ParsedLeaf, ProductExplanation } from "./contracts";
import { readable } from "./wording";

export const PRESENTATION_VERSION = "1.2.0";
export type ReviewStatus = "Required context/metadata action" | "Supported semantic concern" | "Incomplete inspection" | "Insufficient application history" | "Outside-policy coverage" | "Failed analysis" | "Not analyzed" | "Human review required" | "Inspection intentionally omitted" | "No change detected within evaluated checks" | "Presentation limitation" | "Intent unresolved" | "Partitioning unresolved" | "Advisory";
export interface ReviewDocument {
  version: typeof PRESENTATION_VERSION;
  system?: ComparisonCell["system"];
  leaf: ParsedLeaf;
  decision: string | null;
  action: string | null;
  rationale: string;
  approval: boolean | null;
  model: ModelExecutionRecord | null;
  explanation: ProductExplanation | null;
  graph: ComparisonCell["graph"];
  trace: unknown;
  ruleIds: string[];
  statuses: ReviewStatus[];
  area: string;
  attention: boolean;
  limitation: string | null;
}
const contextActions = new Set(["CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT", "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD", "DECLARE_MANUFACTURER_PARTITIONING", "DECLARE_METADATA_MIGRATION_INTENT"]);
const knownActions = new Set([...contextActions, "AUTHOR_REVIEW_HEADING_MAPPING", "HUMAN_VERIFY_STALE_CONTENT", "NO_MATERIAL_REPAIR", "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS", "SELECT_SUPPORTED_REUSE_OPERATION", "VERIFY_HYPERLINK_RELEVANCE", "WAIT_FOR_OPERATIONAL_AVAILABILITY", "COMPLETE_DOCUMENT_INSPECTION"]);
const knownDecisions = new Set(["REUSE_AS_LEGACY_REFERENCE", "REUSE_WITH_NEW_CONTEXT", "REUSE_AFTER_METADATA_REPAIR", "BREAK_LIFECYCLE_AND_RESUBMIT", "DO_NOT_REUSE", "HUMAN_REGULATORY_REVIEW"]);
const supportedPairs: Record<string, Set<string>> = {
  REUSE_AS_LEGACY_REFERENCE: new Set(["NO_MATERIAL_REPAIR", "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS"]),
  REUSE_WITH_NEW_CONTEXT: new Set(["CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT", "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD"]),
  HUMAN_REGULATORY_REVIEW: new Set(["AUTHOR_REVIEW_HEADING_MAPPING", "DECLARE_MANUFACTURER_PARTITIONING", "DECLARE_METADATA_MIGRATION_INTENT", "HUMAN_VERIFY_STALE_CONTENT", "SELECT_SUPPORTED_REUSE_OPERATION", "VERIFY_HYPERLINK_RELEVANCE", "WAIT_FOR_OPERATIONAL_AVAILABILITY", "COMPLETE_DOCUMENT_INSPECTION"]),
};
export function projectDocument(input: Omit<ReviewDocument, "version" | "statuses" | "area" | "attention" | "limitation">, failed = false): ReviewDocument {
  const statuses: ReviewStatus[] = [];
  const { leaf, model, explanation, decision, action } = input;
  const findings = explanation?.findings ?? [];
  const semantic = findings.some(f => f.verification_basis === "semantic_inference" || f.enforcement_mode === "semantic_signal");
  const context = Boolean(action && (contextActions.has(action) || decision === "REUSE_AFTER_METADATA_REPAIR" || decision === "BREAK_LIFECYCLE_AND_RESUBMIT"));
  if (failed || model?.status === "failed") statuses.push("Failed analysis");
  else if (!decision) statuses.push("Not analyzed");
  if (leaf.policy_coverage_status === "INSUFFICIENT_APPLICATION_HISTORY") statuses.push("Insufficient application history");
  if (leaf.policy_coverage_status === "OUTSIDE_ENCODED_POLICY_COVERAGE") statuses.push("Outside-policy coverage");
  if (model?.status === "abstained" || leaf.policy_coverage_status === "DOCUMENT_INSPECTION_INCOMPLETE" || action === "COMPLETE_DOCUMENT_INSPECTION") statuses.push("Incomplete inspection");
  if (model?.status === "not_applicable") statuses.push(model.model_profile_id === "model-free" ? "Inspection intentionally omitted" : "Incomplete inspection");
  if (!failed && model?.status !== "failed" && decision) {
    if (context && action !== "DECLARE_METADATA_MIGRATION_INTENT" && action !== "DECLARE_MANUFACTURER_PARTITIONING") statuses.push("Required context/metadata action");
    if (action === "DECLARE_METADATA_MIGRATION_INTENT") statuses.push("Intent unresolved");
    if (action === "DECLARE_MANUFACTURER_PARTITIONING") statuses.push("Partitioning unresolved");
    if (findings.some(f => f.enforcement_mode === "advisory")) statuses.push("Advisory");
    if (semantic) statuses.push("Supported semantic concern");
    if (input.approval || decision === "HUMAN_REGULATORY_REVIEW") statuses.push("Human review required");
    if (!statuses.length && decision === "REUSE_AS_LEGACY_REFERENCE" && action === "NO_MATERIAL_REPAIR" && model?.status === "completed" && !findings.length && !explanation?.uncertainty?.length) statuses.push("No change detected within evaluated checks");
  }
  const limitation = (!statuses.length || Boolean(decision && (!knownDecisions.has(decision) || !action || !knownActions.has(action) || !supportedPairs[decision]?.has(action)))) ? "This recorded combination has no simplified presentation. Review its recommendation, limitations, and technical record." : null;
  if (limitation) statuses.push("Presentation limitation");
  const area = failed ? "Analysis service" : context ? "Metadata review" : semantic ? "Document content" : statuses.includes("Insufficient application history") ? "Application history" : statuses.includes("Outside-policy coverage") ? "Policy coverage" : statuses.includes("Incomplete inspection") || statuses.includes("Inspection intentionally omitted") ? "Document inspection" : "Reuse review";
  return { ...input, ...((failed || model?.status === "failed") ? { decision: null, action: null, approval: null } : {}), version: PRESENTATION_VERSION, statuses, area, limitation, attention: statuses.some(s => s !== "No change detected within evaluated checks") };
}
export function dossierDocuments(inventory: ApplicationInventory, run: DossierAnalysisRun): ReviewDocument[] {
  return inventory.leaves.map(leaf => {
    const item = run.results.find(r => r.leaf_id === leaf.id);
    const failure = run.failures.find(r => r.leaf_id === leaf.id);
    const a = item?.analysis;
    return projectDocument({ leaf, decision: a?.decision ?? null, action: a?.repair.type ?? null,
      rationale: a?.rationale ?? (failure ? "The service could not complete this analysis. No regulatory decision was issued." : "This document has not been analyzed."),
      approval: a?.human_approval_required ?? null, model: item?.model ?? null,
      explanation: item?.explanation ?? (a ? { version: "1.0.0", findings: a.findings, repair: a.repair, evidence: a.evidence, sources: [], uncertainty: a.unresolved_uncertainty, confidence: a.confidence, limitations: ["Source metadata unavailable in this historical product record."] } : null),
      graph: item?.graph ?? null, trace: a?.trace ?? failure ?? null, ruleIds: a?.triggered_rule_ids ?? [],
    }, Boolean(failure));
  });
}
export function comparisonDocument(leaf: ParsedLeaf, cell: ComparisonCell): ReviewDocument {
  return projectDocument({ leaf, system: cell.system, decision: cell.decision, action: cell.action, rationale: cell.rationale ?? "No completed explanation is available.", approval: cell.human_review_required, model: cell.model, explanation: cell.explanation ?? null, graph: cell.graph, trace: cell.trace, ruleIds: cell.rule_ids }, cell.status !== "completed");
}
export function nextStep(d: ReviewDocument): string {
  if (d.statuses.includes("Failed analysis")) return "Ask the service operator to resolve the execution error, then retry analysis.";
  if (!d.decision) return "Select this document for analysis.";
  return d.explanation?.repair?.description ?? (d.action ? `Review the recorded recommendation: ${readable(d.action)}.` : "A next step was not supplied.");
}

export type ReviewArea = "Document placement" | "Manufacturer metadata" | "Applicant information" | "Document content" | "Recorded check" | "Document inspection" | "Policy coverage" | "Application history" | "Reuse review" | "Analysis service" | "Analysis pending";
export interface DocumentReviewItem {
  id: string;
  area: ReviewArea;
  found: string;
  next: string;
  findingIds: string[];
  statuses: ReviewStatus[];
  qualifications: Array<"inspection_incomplete" | "inspection_omitted" | "approval_required">;
}
export interface ReviewItem extends DocumentReviewItem { key: string; documents: ReviewDocument[] }

export function statusLabel(status: ReviewStatus): string {
  const labels: Partial<Record<ReviewStatus, string>> = {
    "Required context/metadata action": "Proposed change",
    "Supported semantic concern": "Content concern",
    "Insufficient application history": "History missing",
    "Outside-policy coverage": "Outside coverage",
    "Human review required": "Approval required",
    "Inspection intentionally omitted": "Inspection omitted (B2)",
    "No change detected within evaluated checks": "No change detected in evaluated checks",
  };
  return labels[status] ?? status;
}

export function compactNextStep(d: ReviewDocument): string {
  const actions: Record<string, string> = {
    COMPLETE_DOCUMENT_INSPECTION: "Complete document inspection before deciding reuse.",
    DECLARE_METADATA_MIGRATION_INTENT: "Confirm the intended metadata migration.",
    DECLARE_MANUFACTURER_PARTITIONING: "Confirm whether manufacturer partitioning is needed.",
    CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD: "Review the proposed metadata context change.",
    PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS: "Retain exact metadata under the recorded conditions.",
    HUMAN_VERIFY_STALE_CONTENT: "Verify the cited content against the target context.",
    VERIFY_HYPERLINK_RELEVANCE: "Verify the cited links for the target context.",
    AUTHOR_REVIEW_HEADING_MAPPING: "Review exact heading evidence before deciding reuse.",
    SELECT_SUPPORTED_REUSE_OPERATION: "Review the intended reuse operation.",
    WAIT_FOR_OPERATIONAL_AVAILABILITY: "Review the operational availability limitation.",
    NO_MATERIAL_REPAIR: "Review the evaluated scope and recorded qualifications.",
  };
  if (d.statuses.includes("Failed analysis")) return "Resolve the service error, then retry analysis.";
  if (!d.decision) return "Select this leaf for analysis.";
  return actions[d.action ?? ""] ?? "Review the complete recorded recommendation.";
}

function intentObservation(d: ReviewDocument): string {
  const plan = d.explanation?.observations?.metadata_plan;
  if (!plan) return "Migration intent is unavailable in this record.";
  if (plan.intent === "preserve-existing-lifecycle") return "Existing lifecycle preservation was selected.";
  if (plan.intent === "unspecified") return "Migration intent is not yet confirmed.";
  return `Metadata normalization was selected.${plan.manufacturer_partitioning === "unknown" ? " Manufacturer partitioning remains unresolved." : ""}`;
}

/** Split observations, never repairs. Every item points to the same document recommendation. */
export function documentReviewItems(d: ReviewDocument): DocumentReviewItem[] {
  if (!d.attention) return [];
  const items: DocumentReviewItem[] = [];
  const add = (id: string, area: ReviewArea, found: string, next = compactNextStep(d), findingIds: string[] = []) => {
    const findings = d.explanation?.findings?.filter(f => findingIds.includes(f.id)) ?? [];
    const statuses: ReviewStatus[] = [];
    if (area === "Analysis service") statuses.push("Failed analysis");
    else if (!d.decision) statuses.push("Not analyzed");
    else {
      if (area === "Document placement" || (area === "Manufacturer metadata" && d.statuses.includes("Required context/metadata action"))) statuses.push("Required context/metadata action");
      if (findings.some(f => f.enforcement_mode === "advisory")) statuses.push("Advisory");
      if (findings.some(f => f.enforcement_mode === "semantic_signal" || f.verification_basis === "semantic_inference")) statuses.push("Supported semantic concern");
      if (area === "Manufacturer metadata") statuses.push(...d.statuses.filter(s => s === "Intent unresolved" || s === "Partitioning unresolved"));
      if (area === "Policy coverage") statuses.push("Outside-policy coverage");
      if (area === "Application history") statuses.push("Insufficient application history");
      statuses.push(...d.statuses.filter(s => s === "Incomplete inspection" || s === "Inspection intentionally omitted" || s === "Human review required" || s === "Presentation limitation"));
    }
    const qualifications: DocumentReviewItem["qualifications"] = [];
    if (statuses.includes("Incomplete inspection")) qualifications.push("inspection_incomplete");
    if (statuses.includes("Inspection intentionally omitted")) qualifications.push("inspection_omitted");
    if (statuses.includes("Human review required")) qualifications.push("approval_required");
    items.push({ id: `${d.system ?? "RegBridge"}:${d.leaf.id}:${id}`, area, found, next, findingIds, statuses, qualifications });
  };
  if (d.statuses.includes("Failed analysis")) {
    add("execution", "Analysis service", "Analysis failed. No regulatory decision was issued.");
    return items;
  }
  if (!d.decision) { add("not-analyzed", "Analysis pending", "This leaf has not been analyzed."); return items; }
  const observed = d.explanation?.observations;
  const handled = new Set<string>();
  for (const p of observed?.placements ?? []) {
    add(`placement-${p.finding_id}`, "Document placement", `Legacy heading ${p.source_heading} is unavailable in the selected target structure. Supported target: ${p.target_heading}.`, `Review proposed context change to ${p.target_heading}.`, [p.finding_id]);
    handled.add(p.finding_id);
  }
  const metadataFindings = observed?.keywords.filter(k => k.keyword_name === "manufacturer").map(k => k.finding_id) ?? [];
  const manufacturer = d.leaf.keywords.filter(k => k.name === "manufacturer");
  const metadataAction = ["DECLARE_METADATA_MIGRATION_INTENT", "DECLARE_MANUFACTURER_PARTITIONING", "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD", "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS"].includes(d.action ?? "");
  if (manufacturer.length && (metadataFindings.length || metadataAction)) {
    const inspection = d.statuses.includes("Incomplete inspection") ? " Content inspection remains incomplete." : "";
    const advisory = d.explanation?.findings?.some(f => metadataFindings.includes(f.id) && f.enforcement_mode === "advisory") ? " Recorded advisory applies." : "";
    add("manufacturer", "Manufacturer metadata", `${manufacturer.map(k => `${k.name}=${JSON.stringify(k.raw_value)}`).join("; ")}. ${intentObservation(d)}${inspection}${advisory}`, compactNextStep(d), metadataFindings);
    metadataFindings.forEach(id => handled.add(id));
  }
  for (const finding of d.explanation?.findings ?? []) {
    if (handled.has(finding.id)) continue;
    const category = observed?.semantic_topics.find(t => t.finding_id === finding.id)?.category;
    const excerpts = d.explanation?.evidence.filter(e => finding.evidence_ids.includes(e.id) && !("source_id" in e));
    const quoted = excerpts?.map(e => `Document text: “${e.text}”`).join(" ");
    const applicant = category === "applicant_name_mismatch";
    add(`finding-${finding.id}`, applicant ? "Applicant information" : finding.verification_basis === "semantic_inference" ? "Document content" : "Recorded check",
      applicant ? `${quoted || "Cited document text unavailable."} Package metadata applicant: ${observed?.package_applicant_name ? `“${observed.package_applicant_name}”.` : "unavailable."}` : quoted || finding.rationale,
      applicant ? "Verify the cited applicant information before reuse." : compactNextStep(d), [finding.id]);
  }
  if (!items.length && (d.statuses.includes("Incomplete inspection") || d.statuses.includes("Inspection intentionally omitted"))) {
    add("inspection", "Document inspection", d.statuses.includes("Inspection intentionally omitted") ? "B2 intentionally omits content inspection." : "Content inspection is incomplete; no content concern is inferred from this limitation.", d.statuses.includes("Inspection intentionally omitted") ? "Review the rules-only recommendation and its capability boundary." : "Complete document inspection before deciding reuse.");
  }
  for (const [status, area] of [["Outside-policy coverage", "Policy coverage"], ["Insufficient application history", "Application history"]] as const) {
    if (d.statuses.includes(status)) add(status, area, d.leaf.policy_coverage_basis);
  }
  if (!items.length) {
    // Direct systems retain their own explanation and supplied citations only.
    const cited = d.explanation?.findings == null ? d.explanation?.evidence.filter(e => !("source_id" in e)).map(e => `Document text: “${e.text}”`).join(" ") : "";
    const applicantInput = observed?.package_applicant_name;
    // A source topic label only; the direct approach's own rationale remains in detail.
    // Do not infer a mismatch or extract a name from the passage.
    const applicantPassage = cited && /\bapplicant\b/i.test(cited);
    const area = applicantPassage ? "Applicant information" : d.action === "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT" ? "Document placement" : "Reuse review";
    const found = applicantPassage ? `${cited} Package metadata applicant: ${applicantInput ? `“${applicantInput}”.` : "unavailable."}` : area === "Document placement" ? `Source heading: ${d.leaf.heading}. A structured target heading was not supplied by this approach.` : cited || d.rationale;
    add("recommendation", area, found);
  }
  return items;
}

export function groupReviewItems(documents: ReviewDocument[]): ReviewItem[] {
  const groups = new Map<string, ReviewItem>();
  for (const d of documents) {
    const occurrences = new Map<string, number>();
    for (const item of documentReviewItems(d)) {
      // Equivalence requires the same observation AND complete recommendation/qualifications.
      const signature = JSON.stringify([d.system ?? "RegBridge", item.area, item.found, item.next, item.statuses, item.qualifications, d.decision, d.action, d.rationale, d.approval, d.statuses, d.explanation?.repair, d.explanation?.uncertainty, d.explanation?.confidence, d.model?.reason_category, d.model?.status_detail, d.leaf.policy_coverage_basis, d.leaf.heading, d.leaf.keywords, d.explanation?.observations?.metadata_plan, d.explanation?.findings?.filter(f => item.findingIds.includes(f.id)).map(f => [f.rule_id, f.rationale, f.severity, f.verification_basis, f.enforcement_mode])]);
      const ordinal = occurrences.get(signature) ?? 0;
      occurrences.set(signature, ordinal + 1);
      const key = JSON.stringify([signature, ordinal]);
      const prior = groups.get(key);
      if (prior && !prior.documents.some(doc => doc.leaf.id === d.leaf.id && doc.system === d.system)) prior.documents.push(d);
      else if (!prior) groups.set(key, { ...item, key, documents: [d] });
    }
  }
  return [...groups.values()];
}

export function overviewFinding(d: ReviewDocument): string {
  return documentReviewItems(d)[0]?.found ?? d.rationale;
}
