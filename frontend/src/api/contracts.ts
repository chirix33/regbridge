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
}

export interface ApplicationInventory {
  id: string;
  fixture_id: string | null;
  source_standard: string;
  application_number: string | null;
  submission_type: string | null;
  applicant_name: string | null;
  has_stf: boolean;
  package_sha256: string;
  leaves: ParsedLeaf[];
  warnings: Array<{ code: string; message: string; locator: string }>;
}

export interface EvidenceSpan {
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
  target_context: { scenario_mode: ScenarioMode };
  operational_status: "not_operational";
  scenario_disclosure: string;
  expert_validated: false;
  decision: string;
  severity: string;
  triggered_rule_ids: string[];
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
