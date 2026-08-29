export type LlmMode = "fixture" | "live" | "disabled";

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
  review_status: "candidate" | "reviewed" | "authoritative_for_demo" | "rejected";
  reviewer_note: string;
}

export interface StandardsSnapshotResponse {
  snapshot_id: string;
  manifest_version: string;
  description: string;
  sources: StandardSourceSummary[];
}

