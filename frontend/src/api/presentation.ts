import type { ApplicationInventory, ComparisonCell, DossierAnalysisRun, ModelExecutionRecord, ParsedLeaf, ProductExplanation } from "./contracts";
import { readable } from "./wording";

export const PRESENTATION_VERSION = "1.0.0";
export type ReviewStatus = "Required context/metadata action" | "Supported semantic concern" | "Incomplete inspection" | "Insufficient application history" | "Outside-policy coverage" | "Failed analysis" | "Not analyzed" | "Human review required" | "Inspection intentionally omitted" | "No change detected within evaluated checks" | "Presentation limitation";
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
  if (!failed && decision) {
    if (context) statuses.push("Required context/metadata action");
    if (semantic) statuses.push("Supported semantic concern");
    if (input.approval || decision === "HUMAN_REGULATORY_REVIEW") statuses.push("Human review required");
    if (!statuses.length && decision === "REUSE_AS_LEGACY_REFERENCE" && action === "NO_MATERIAL_REPAIR" && model?.status === "completed" && !findings.length && !explanation?.uncertainty?.length) statuses.push("No change detected within evaluated checks");
  }
  const limitation = (!statuses.length || Boolean(decision && (!knownDecisions.has(decision) || !action || !knownActions.has(action) || !supportedPairs[decision]?.has(action)))) ? "This recorded combination has no simplified presentation. Review its recommendation, limitations, and technical record." : null;
  if (limitation) statuses.push("Presentation limitation");
  const area = failed ? "Analysis service" : context ? "Context and metadata" : semantic ? "Document content" : statuses.includes("Insufficient application history") ? "Application history" : statuses.includes("Outside-policy coverage") ? "Policy coverage" : statuses.includes("Incomplete inspection") || statuses.includes("Inspection intentionally omitted") ? "Document inspection" : "Reuse review";
  return { ...input, version: PRESENTATION_VERSION, statuses, area, limitation, attention: statuses.some(s => s !== "No change detected within evaluated checks") };
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
export interface ReviewItem { key: string; documents: ReviewDocument[] }
export function groupReviewItems(documents: ReviewDocument[]): ReviewItem[] {
  const groups = new Map<string, ReviewDocument[]>();
  for (const d of documents) {
    // Exact equivalence only. IDs and locators stay on each document; no prose parsing.
    const key = JSON.stringify([d.area, d.decision, d.action, d.rationale, d.approval, d.statuses, [d.explanation?.repair?.type, d.explanation?.repair?.description], d.explanation?.uncertainty, d.explanation?.confidence, d.model?.reason_category, d.model?.status_detail, d.leaf.policy_coverage_basis, d.leaf.heading, d.leaf.keywords.map(k => [k.name, k.raw_value]), d.explanation?.findings?.map(f => [f.rule_id, f.rationale, f.severity, f.verification_basis, f.enforcement_mode])]);
    groups.set(key, [...(groups.get(key) ?? []), d]);
  }
  return [...groups].map(([key, documents]) => ({ key, documents }));
}
export function nextStep(d: ReviewDocument): string {
  if (d.statuses.includes("Failed analysis")) return "Ask the service operator to resolve the execution error, then retry analysis.";
  if (!d.decision) return "Select this document for analysis.";
  return d.explanation?.repair?.description ?? (d.action ? `Review the recorded recommendation: ${readable(d.action)}.` : "A next step was not supplied.");
}

export function overviewFinding(d: ReviewDocument): string {
  if (d.statuses.includes("Failed analysis")) return "The service could not complete the analysis; no regulatory decision was issued.";
  if (d.statuses.includes("Outside-policy coverage") || d.statuses.includes("Insufficient application history")) return d.leaf.policy_coverage_basis;
  if (d.statuses.includes("Supported semantic concern")) {
    const content = d.explanation?.findings?.filter(f => f.verification_basis === "semantic_inference" || f.enforcement_mode === "semantic_signal").map(f => f.rationale).join(" ") || d.rationale;
    return d.statuses.includes("Required context/metadata action") ? `The recorded check also requires a context or metadata action. ${content}` : content;
  }
  if (d.action === "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT") return "The recorded placement check requires a new target context for this document.";
  if (d.action === "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD") return "The recorded metadata change requires a new target context group.";
  if (d.action === "DECLARE_METADATA_MIGRATION_INTENT") return "The metadata recommendation depends on whether you intend to preserve or change the existing metadata.";
  if (d.action === "PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS") return "The recommendation retains exact existing metadata and its recorded qualifications.";
  return d.rationale;
}
