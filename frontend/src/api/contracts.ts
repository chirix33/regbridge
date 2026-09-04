export type LlmMode = "fixture" | "live" | "disabled";
export type ScenarioMode = "prospective_forward_compatibility" | "current_operational";

export interface ScopeResponse {
  product_name: "RegBridge";
  product_type: "research prototype" | "risk analyzer" | "decision support";
  research_question: string;
  authority: "FDA";
  center: "CDER";
  supported_application_types: string[];
  source_standards: string[];
  target_standards: string[];
  standards_snapshot_id: string;
  model_mode: LlmMode;
  network_required: boolean;
  operational_status: "not_operational";
  approved_research_scenario: ScenarioMode;
  expert_validated: false;
  available_features: string[];
  planned_archetypes: string[];
  disclaimer: string;
  limitations: string[];
}

export interface StandardSourceSummary {
  id: string;
  title: string;
  version: string;
  authority: "FDA";
  center: "CDER";
  source_url: string;
  sha256: string;
  review_status: "candidate" | "source_verified" | "author_adjudicated_for_demo" | "rejected";
  verification_basis: string;
  enforcement_mode: string;
  expert_validated: false;
  reviewer_note: string;
}

export interface StandardsSnapshotResponse {
  snapshot_id: string;
  manifest_version: string;
  description: string;
  sources: StandardSourceSummary[];
}

export interface FixtureSummary {
  id: string;
  title: string;
  description: string;
  expected_class: "positive" | "negative" | "ambiguous";
  archetype: "unavailable-heading" | "legacy-metadata-tension" | "stale-content-or-hyperlink";
  default_metadata_intent: MetadataIntent | null;
  manufacturer_partitioning: ManufacturerPartitioning | null;
  replacement_manufacturer_value: string | null;
  author_verified_relevant_hyperlink_ids: string[];
}

export type MetadataIntent = "preserve-existing-lifecycle" | "normalize-metadata" | "unspecified";
export type ManufacturerPartitioning = "unnecessary" | "required" | "unknown";

export interface MetadataPlan {
  intent: MetadataIntent;
  manufacturer_partitioning: ManufacturerPartitioning;
  replacement_manufacturer_value: string | null;
}

export interface FixtureListResponse {
  fixtures: FixtureSummary[];
}

export interface ParsedLeaf {
  id: string;
  title: string;
  heading: string;
  href: string;
  operation: string;
  content_type: string;
  file_sha256: string;
  source_locator: string;
  keywords: Array<{
    name: string;
    raw_value: string;
    normalized_value: string;
    source_locator: string;
  }>;
  text_span_count: number;
  hyperlink_count: number;
  extraction_status: "completed" | "failed" | "bounded";
  raw_heading: string | null;
  heading_status: "recognized" | "unsupported";
  declared_checksum_type: "md5" | "sha256" | null;
  declared_checksum: string | null;
  computed_declared_checksum: string | null;
  declared_checksum_matches: boolean | null;
  policy_coverage_status: "EVALUATED_WITH_APPROVED_POLICY" | "NO_MIGRATION_CHANGE_DETECTED" | "OUTSIDE_ENCODED_POLICY_COVERAGE" | "INSUFFICIENT_APPLICATION_HISTORY" | "DOCUMENT_INSPECTION_INCOMPLETE";
  policy_coverage_basis: string;
  covered_policy_ids: string[];
}

export interface ApplicationInventory {
  id: string;
  fixture_id: string | null;
  source_standard: string;
  application_number: string | null;
  submission_type: string | null;
  application_type_code: string | null;
  submission_id: string | null;
  sequence_number: string | null;
  applicant_name: string | null;
  has_stf: boolean;
  package_sha256: string;
  leaves: ParsedLeaf[];
  warnings: Array<{ code: string; message: string; locator: string }>;
  input_profile_id: string;
  input_profile_version: string;
  detected_sequence_root: string;
  layout: "authentic_sequence_layout" | "legacy_controlled_layout";
  parsing_extent: "complete" | "bounded";
  package_profile_status: "passed" | "warning" | "unsupported" | "failed";
  profile_checks: Array<{ id: string; label: string; status: "passed" | "warning" | "unsupported" | "failed"; detail: string }>;
  xml_declarations: Array<{ path: string; root_name: string; namespace: string | null; declared_doctype: string | null; doctype_recognized: boolean; dtd_version_supported: boolean; dtd_validation_performed: boolean; dtd_validation_result: "not_performed" | "passed" | "failed"; dtd_asset_id: string | null; effective_dtd_version: string | null; version_source: "declared" | "inferred_from_catalog" | "unsupported" }>;
  package_files: Array<{ path: string; member_type: string; provenance_sha256: string; relationship: string }>;
  policy_coverage_counts: Record<string, number>;
  regional_xml_version: string | null;
  regional_xml_sha256: string | null;
  index_md5_declared: string | null;
  index_md5_computed: string | null;
  index_md5_matches: boolean | null;
}

export interface ModelProfile {
  model_id: string;
  display_name: string;
  subtitle: string | null;
  availability: "available" | "coming_soon" | "misconfigured";
  disabled_reason: string | null;
  adapter_type: "responses" | "chat_completions";
  configured_model_name: string | null;
  structured_output_capability: "validated" | "unvalidated";
  reasoning_capability: boolean;
  configuration_digest: string;
  network_required: boolean;
}

export interface ModelCatalog { default_model_id: string; models: ModelProfile[] }

export interface TargetContext {
  authority: "FDA";
  center: "CDER";
  application_type: "NDA";
  source_standard: "eCTD-3.2.2";
  target_standard: "eCTD-4.0";
  analysis_date: string;
  reuse_operation: "reference-existing-content";
  standards_snapshot_id: "fda-cder-demo-v1";
  scenario_mode: ScenarioMode;
  metadata_plan: MetadataPlan;
}

export interface ModelExecutionRecord {
  model_profile_id: string;
  requested_model_name: string | null;
  provider_reported_model_name: string | null;
  adapter_type: string;
  configuration_digest: string;
  prompt_version: string;
  request_digest: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  latency_ms: number;
  status: string;
  failure: string | null;
}

export interface DossierLeafResult {
  leaf_id: string;
  analysis_ref: string;
  analysis: AnalysisResult;
  graph: GraphNeighborhood;
  model: ModelExecutionRecord;
}

export interface DossierAnalysisRun {
  run_id: string;
  state: "queued" | "running" | "completed" | "partial_failed" | "failed";
  inventory_id: string;
  input_profile_id: string;
  selected_model: ModelProfile;
  execution_configuration_digest: string;
  requested_leaf_ids: string[];
  summary: null | {
    package_sha256: string;
    application_number: string | null;
    submission_type: string | null;
    applicant_name: string | null;
    total_supported_leaves: number;
    analyzed_count: number;
    failed_count: number;
    skipped_count: number;
    decision_counts: Record<string, number>;
    severity_counts: Record<string, number>;
    human_approval_count: number;
    parser_warning_count: number;
    policy_coverage_counts: Record<string, number>;
  };
  results: DossierLeafResult[];
  failures: Array<{ leaf_id: string; stage: string; cause: string; retryable: boolean }>;
  operational_status: "not_operational";
  expert_validated: false;
  capability_boundary: string;
}

export interface ComparisonCell {
  leaf_id: string;
  system: "B0" | "B1" | "B2" | "RegBridge";
  model: ModelExecutionRecord;
  decision: string | null;
  severity: string | null;
  action: string | null;
  human_review_required: boolean | null;
  rationale: string | null;
  evidence_ids: string[];
  rule_ids: string[];
  retrieval: Array<{ alias: string; evidence_id: string; score: number; rank: number }>;
  graph: GraphNeighborhood | null;
  trace: Array<Record<string, unknown>>;
  status: "completed" | "invalid_output" | "failed";
  failure: string | null;
}

export interface ComparisonRun {
  comparison_id: string;
  state: "queued" | "running" | "completed" | "partial_failed" | "failed";
  inventory_id: string;
  selected_model: ModelProfile;
  requested_leaf_ids: string[];
  results: ComparisonCell[];
  failures: Array<{ leaf_id: string; stage: string; cause: string }>;
  operational_status: "not_operational";
  expert_validated: false;
  benchmark_evaluation: false;
}

export interface RegulatoryEvidenceSpan {
  id: string;
  source_id: string;
  locator: string;
  text: string;
  bindingness: string;
  source_sha256: string;
  review_status: string;
  verification_basis: string;
  enforcement_mode: string;
  expert_validated: boolean;
}

export interface DossierEvidence {
  id: string;
  artifact_id: string;
  kind: "text" | "hyperlink" | "metadata";
  locator: string;
  text: string;
  file_sha256: string;
  extraction_method: "deterministic";
}

export type EvidenceSpan = RegulatoryEvidenceSpan | DossierEvidence;

export interface AnalysisResult {
  id: string;
  source_artifact: {
    id: string;
    title: string;
    source_leaf_id: string;
    source_heading: string;
    source_locator: string;
    file_sha256: string;
  };
  target_context: { scenario_mode: ScenarioMode; metadata_plan: MetadataPlan | null };
  operational_status: "not_operational";
  scenario_disclosure: string;
  expert_validated: false;
  decision: string;
  severity: string;
  triggered_rule_ids: string[];
  findings: Array<{
    id: string;
    rule_id: string | null;
    severity: string;
    rationale: string;
    evidence_ids: string[];
    source: string;
    verification_basis: string;
    enforcement_mode: string;
  }>;
  evidence: EvidenceSpan[];
  rationale: string;
  repair: { type: string; description: string; evidence_ids: string[] };
  confidence: number;
  unresolved_uncertainty: string[];
  human_approval_required: boolean;
  trace: Array<{
    sequence: number;
    kind: string;
    component: string;
    summary: string;
    evidence_ids: string[];
  }>;
  model_run: {
    mode: LlmMode;
    status: "completed" | "abstained" | "failed" | "not_applicable";
    prompt_template_version: string;
    model_name: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    latency_ms: number;
    validation_error: string | null;
  };
}

export interface GraphNeighborhood {
  analysis_id: string;
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    version: string | null;
    review_status: string | null;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    type: string;
    label: string;
    evidence_ids: string[];
    review_status: string | null;
  }>;
  text_alternative: string[];
}

export interface PresentationRate {
  numerator: number;
  denominator: number;
  rate: number | null;
}

export interface PresentationMetricReport {
  system: "B0" | "B1" | "B2" | "RegBridge";
  repetition_index: number | null;
  result_status: string;
  accuracy: number;
  macro_f1: number;
  unsafe_false_negative_rate: PresentationRate;
  review_bypass_rate: PresentationRate;
  outside_represented_rate: number | null;
  invalid_outputs: number;
  invalid_output_rate: number;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  latency_ms_total: number;
  cost_usd: number | null;
  retrieval: {
    result_status: string;
    evaluated_cases: number;
    recall_at_3: number | null;
    precision_at_3: number | null;
    mrr: number | null;
  } | null;
  family_sensitivity: Array<{
    fixture_family: string;
    unsafe_misses: number;
    eligible_cases: number;
  }>;
}

export interface PresentationCasePrediction {
  system: "B0" | "B1" | "B2" | "RegBridge";
  repetition_index: number | null;
  result_status: string;
  outcome: string;
  decision: string;
  action: string;
  human_review_required: boolean;
  evidence_ids: string[];
  rule_ids: string[];
  unsafe_false_negative: boolean;
  review_bypass: boolean;
  outside_represented_class: boolean;
  cost_usd: number | null;
  latency_ms: number;
  requests: number;
  failure: string | null;
}

export interface PresentationCaseTrace {
  case_id: string;
  fixture_id: string;
  fixture_family: string;
  archetype: string;
  split: "test";
  selected_leaf_id: string;
  reference_decision: string;
  reference_action: string;
  reference_severity: string;
  reference_human_review_required: boolean;
  mutation: Record<string, string>;
  package_sha256: string;
  selected_file_sha256: string;
  decision_fingerprint_sha256: string;
  predictions: PresentationCasePrediction[];
  varied_predictions: boolean;
}

export interface DemoPreset {
  id: string;
  route: "/demo/case-a" | "/demo/case-b" | "/demo/case-c";
  label: string;
  fixture_id: string;
  purpose: string;
  primary_path: boolean;
  scenario_mode: "prospective_forward_compatibility";
  metadata_plan: Record<string, string | null> | null;
}

export interface M4PresentationSnapshot {
  schema_version: "m4.presentation.v1";
  snapshot_version: string;
  snapshot_sha256: string;
  source_run_id: string;
  source_run_directory: string;
  source_run_file_sha256: Record<string, string>;
  predictions_sha256: string;
  metrics_sha256: string;
  repository_commit: string;
  benchmark_sha256: string;
  frozen_prompt_digest: string;
  frozen_configuration_digest: string;
  run_type: "live_model_run";
  empirical_model_run: true;
  eligible_for_performance_claims: true;
  current_fda_operational_availability: "not_operational";
  expert_validated: false;
  headline_scope: "held-out-test";
  disclosure: string;
  limitations: string[];
  completion_audit: Record<string, unknown>;
  metric_reports: PresentationMetricReport[];
  metric_ranges: Record<string, Record<string, { min: number; max: number }>>;
  retrieval_summary: {
    result_status: string;
    per_repetition: Array<{
      repetition_index: number;
      recall_at_3: number | null;
      precision_at_3: number | null;
      mrr: number | null;
      evaluated_cases: number;
    }>;
  } | null;
  usage_summary: Record<string, Record<string, unknown>>;
  cost_summary: Record<string, unknown>;
  cases: PresentationCaseTrace[];
  demo_presets: DemoPreset[];
  graph_contract_disclosure: string;
  correction_ledger_path: string;
}

export interface M4PresentationResponse {
  snapshot: M4PresentationSnapshot;
}

export interface M4PresentationCasesResponse {
  snapshot_version: string;
  source_run_id: string;
  cases: PresentationCaseTrace[];
}

export interface DemoPresetsResponse {
  presets: DemoPreset[];
}
