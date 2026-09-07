const labels: Record<string, string> = {
  REUSE_AS_LEGACY_REFERENCE: "Reuse as a legacy reference",
  REUSE_WITH_NEW_CONTEXT: "Reuse with a new context",
  REUSE_AFTER_METADATA_REPAIR: "Repair metadata before reuse",
  BREAK_LIFECYCLE_AND_RESUBMIT: "Start a new lifecycle and resubmit",
  DO_NOT_REUSE: "Do not reuse",
  HUMAN_REGULATORY_REVIEW: "Regulatory review needed",
  EVALUATED_WITH_APPROVED_POLICY: "Covered by the research rules",
  NO_MIGRATION_CHANGE_DETECTED: "No migration change detected",
  OUTSIDE_ENCODED_POLICY_COVERAGE: "Outside the available rules",
  INSUFFICIENT_APPLICATION_HISTORY: "More application history needed",
  DOCUMENT_INSPECTION_INCOMPLETE: "Document inspection incomplete",
  COMPLETE_DOCUMENT_INSPECTION: "Complete the document inspection",
  CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT: "Create a new context group and suspend the legacy content",
  abstained: "Inspection incomplete",
  not_applicable: "Not run for this analysis",
  partial_failed: "Finished with some failures",
  failed: "Could not complete",
  invalid_output: "Response could not be validated",
  completed: "Completed",
  not_operational: "Currently unavailable",
};

export function readable(value: string | null | undefined): string {
  if (!value) return "Not available";
  return labels[value] ?? (value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()).replaceAll("_", " ");
}

export function errorMessage(cause: unknown): string {
  if (cause instanceof TypeError) return "We couldn't connect to RegBridge. Check that the local service is running, then try again.";
  return cause instanceof Error ? cause.message : "We couldn't complete this step. Please try again.";
}
