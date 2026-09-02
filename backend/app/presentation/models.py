from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.models import DomainModel, Sha256, StableId


class PresentationRate(DomainModel):
    numerator: int
    denominator: int
    rate: float | None


class PresentationMetricReport(DomainModel):
    system: Literal["B0", "B1", "B2", "RegBridge"]
    repetition_index: int | None
    result_status: str
    accuracy: float
    macro_f1: float
    unsafe_false_negative_rate: PresentationRate
    review_bypass_rate: PresentationRate
    outside_represented_rate: float | None
    invalid_outputs: int
    invalid_output_rate: float
    requests: int
    input_tokens: int
    output_tokens: int
    latency_ms_total: float
    cost_usd: float | None
    retrieval: dict[str, Any] | None = None
    family_sensitivity: tuple[dict[str, Any], ...] = ()


class PresentationCasePrediction(DomainModel):
    system: Literal["B0", "B1", "B2", "RegBridge"]
    repetition_index: int | None
    result_status: str
    outcome: str
    decision: str
    action: str
    human_review_required: bool
    evidence_ids: tuple[StableId, ...]
    rule_ids: tuple[StableId, ...] = ()
    unsafe_false_negative: bool
    review_bypass: bool
    outside_represented_class: bool
    cost_usd: float | None
    latency_ms: float
    requests: int
    failure: str | None = None


class PresentationCaseTrace(DomainModel):
    case_id: StableId
    fixture_id: StableId
    fixture_family: StableId
    archetype: str
    split: Literal["test"]
    selected_leaf_id: StableId
    reference_decision: str
    reference_action: str
    reference_severity: str
    reference_human_review_required: bool
    mutation: dict[str, str]
    package_sha256: Sha256
    selected_file_sha256: Sha256
    decision_fingerprint_sha256: Sha256
    predictions: tuple[PresentationCasePrediction, ...]
    varied_predictions: bool


class DemoPreset(DomainModel):
    id: StableId
    route: Literal["/demo/case-a", "/demo/case-b", "/demo/case-c"]
    label: str
    fixture_id: StableId
    purpose: str
    primary_path: bool
    scenario_mode: Literal["prospective_forward_compatibility"]
    metadata_plan: dict[str, str | None] | None = None


class M4PresentationSnapshot(DomainModel):
    schema_version: Literal["m4.presentation.v1"]
    snapshot_version: StableId
    snapshot_sha256: Sha256 | None = None
    source_run_id: StableId
    source_run_directory: str
    source_run_file_sha256: dict[str, Sha256]
    repository_commit: str
    benchmark_sha256: Sha256
    frozen_prompt_digest: Sha256
    frozen_configuration_digest: Sha256
    generated_from: dict[str, str]
    run_type: Literal["live_model_run"]
    empirical_model_run: Literal[True]
    eligible_for_performance_claims: Literal[True]
    current_fda_operational_availability: Literal["not_operational"]
    expert_validated: Literal[False]
    headline_scope: Literal["held-out-test"]
    disclosure: str
    limitations: tuple[str, ...]
    completion_audit: dict[str, Any]
    metric_reports: tuple[PresentationMetricReport, ...]
    metric_ranges: dict[str, dict[str, dict[str, float]]]
    retrieval_summary: dict[str, Any] | None
    usage_summary: dict[str, Any]
    cost_summary: dict[str, Any]
    cases: tuple[PresentationCaseTrace, ...] = Field(min_length=12, max_length=12)
    demo_presets: tuple[DemoPreset, ...]
    graph_contract_disclosure: str
    correction_ledger_path: str

    @model_validator(mode="after")
    def validate_m4_contract(self) -> "M4PresentationSnapshot":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("presentation snapshot case IDs must be unique")
        if self.current_fda_operational_availability != "not_operational":
            raise ValueError("M4 may not change FDA operational availability")
        if self.expert_validated:
            raise ValueError("M4 snapshot cannot claim expert validation")
        if any(case.split != "test" for case in self.cases):
            raise ValueError("M4 headline snapshot must contain held-out test cases only")
        return self


class M4PresentationResponse(DomainModel):
    snapshot: M4PresentationSnapshot


class M4PresentationCasesResponse(DomainModel):
    snapshot_version: StableId
    source_run_id: StableId
    cases: tuple[PresentationCaseTrace, ...]


class DemoPresetsResponse(DomainModel):
    presets: tuple[DemoPreset, ...]

