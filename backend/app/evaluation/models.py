from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.enums import Decision, ReviewStatus, Severity
from app.domain.models import (
    DomainModel,
    DossierEvidence,
    ReviewEvent,
    Sha256,
    StableId,
    TargetContext,
)

SystemName = Literal["B0", "B1", "B2", "RegBridge"]
RunState = Literal["queued", "running", "completed", "failed"]


class CaseInput(DomainModel):
    """Inference input. Reference labels and adjudication rationales are intentionally absent."""

    case_id: StableId
    fixture_id: StableId
    selected_leaf_id: StableId
    target_context_id: StableId
    target_context: TargetContext
    package_sha256: Sha256
    selected_file_sha256: Sha256
    material: dict[str, Any]
    dossier_evidence: tuple[DossierEvidence, ...] = ()


class ReferenceLabel(DomainModel):
    decision: Decision
    severity: Severity
    action: StableId
    action_mode: Literal["required_condition", "suggested_check", "no_action"]
    required_rule_ids: tuple[StableId, ...]
    acceptable_evidence_ids: tuple[StableId, ...]
    human_review_required: bool
    rationale: str = Field(min_length=1)


class BenchmarkCase(DomainModel):
    case_id: StableId
    archetype: str
    fixture_id: StableId
    source_fixture_id: StableId | None
    selected_leaf_id: StableId
    target_context_id: StableId
    target_context: TargetContext
    fixture_family: StableId
    split: Literal["train", "development", "test"]
    mutation: dict[str, str]
    package_sha256: Sha256
    selected_file_sha256: Sha256
    target_context_sha256: Sha256
    decision_fingerprint_sha256: Sha256
    decision_predicate_sha256: Sha256
    decision_relevant_predicates: dict[str, Any]
    reference: ReferenceLabel
    review_status: Literal[ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO]
    review_event: ReviewEvent
    expert_validated: Literal[False] = False

    def to_case_input(self) -> CaseInput:
        predicates = self.decision_relevant_predicates
        material = {
            key: value
            for key, value in predicates.items()
            if key not in {"package_sha256", "selected_file_sha256"}
        }
        return CaseInput(
            case_id=self.case_id,
            fixture_id=self.fixture_id,
            selected_leaf_id=self.selected_leaf_id,
            target_context_id=self.target_context_id,
            target_context=self.target_context,
            package_sha256=self.package_sha256,
            selected_file_sha256=self.selected_file_sha256,
            material=material,
        )


class FrozenBenchmark(DomainModel):
    schema_version: Literal["1.0.0"]
    benchmark_version: str
    snapshot_id: StableId
    status: Literal["frozen"]
    frozen_at: str
    source_ledger_sha256: Sha256
    frozen_by: Literal["author-01"]
    expert_validated: Literal[False]
    operational_availability: Literal["not_operational"]
    cases: tuple[BenchmarkCase, ...] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_frozen_distribution(self) -> "FrozenBenchmark":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("frozen benchmark case identifiers must be unique")
        test = [case for case in self.cases if case.split == "test"]
        if len(test) != 12 or len({case.fixture_family for case in test}) != 6:
            raise ValueError("frozen test set must have 12 cases across six families")
        return self


class DirectDecisionOutput(DomainModel):
    decision: Decision
    severity: Severity
    action: StableId
    human_review_required: bool
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)


class RetrievalHit(DomainModel):
    evidence_id: StableId
    score: float
    rank: int = Field(ge=1)


class RetrievalTrace(DomainModel):
    system: Literal["B1"] = "B1"
    case_id: StableId
    query: str
    query_sha256: Sha256
    corpus_sha256: Sha256
    configuration_sha256: Sha256
    top_k: Literal[3] = 3
    k1: float = 1.5
    b: float = 0.75
    idf_formula: Literal["log(1+(N-df+0.5)/(df+0.5))"]
    hits: tuple[RetrievalHit, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_fixed_configuration(self) -> "RetrievalTrace":
        if self.k1 != 1.5 or self.b != 0.75:
            raise ValueError("M3 BM25 traces require k1=1.5 and b=0.75")
        return self


class SystemPrediction(DomainModel):
    system: SystemName
    case_id: StableId
    decision: Decision
    severity: Severity
    action: StableId
    human_review_required: bool
    unconditional_reuse: bool
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()
    rule_ids: tuple[StableId, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    prediction_source: Literal["contract_fixture", "genuine_rule_only", "hybrid_contract_fixture"]
    empirical_model_observation: Literal[False] = False
    latency_ms: float = Field(ge=0)
    requests: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    failure: str | None = None


class ClassMetrics(DomainModel):
    precision: float
    recall: float
    f1: float
    support: int


class RateMetric(DomainModel):
    numerator: int
    denominator: int
    rate: float | None
    wilson_95_low: float | None
    wilson_95_high: float | None


class RetrievalMetrics(DomainModel):
    evaluated_cases: int
    recall_at_3: float | None
    precision_at_3: float | None
    mrr: float | None


class FamilySensitivity(DomainModel):
    fixture_family: StableId
    unsafe_misses: int
    eligible_cases: int


class MetricsReport(DomainModel):
    system: SystemName
    scope: Literal["held-out-test", "all-cases-secondary"]
    represented_classes: tuple[Decision, ...]
    unsafe_false_negative_rate: RateMetric
    high_blocking_unsafe_false_negative_rate: RateMetric
    review_bypass_rate: RateMetric
    conservative_false_positive_rate: RateMetric
    per_class: dict[str, ClassMetrics]
    macro_f1: float
    accuracy: float
    balanced_accuracy: float
    heading_mapping_accuracy: float | None
    evidence_citation_accuracy: float
    repair_action_accuracy: float
    abstention_accuracy: float
    retrieval: RetrievalMetrics | None
    latency_ms_total: float
    failures: int
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    calibration_status: Literal["not_applicable"]
    calibration_not_applicable_reason: str
    family_sensitivity: tuple[FamilySensitivity, ...]
    cluster_bootstrap_unsafe_fnr_95: tuple[float, float] | None
    inference_claims: Literal["exploratory-only-no-independence-or-significance-claims"]


class CaseEvaluation(DomainModel):
    case_id: StableId
    fixture_family: StableId
    split: str
    system: SystemName
    reference_decision: Decision
    prediction_decision: Decision
    reference_action: StableId
    prediction_action: StableId
    unsafe_false_negative: bool
    review_bypass: bool
    conservative_false_positive: bool
    correct: bool


class EvaluationArtifacts(DomainModel):
    run_directory: str
    manifest_json: str
    predictions_jsonl: str
    retrieval_jsonl: str
    per_case_csv: str
    metrics_json: str
    metrics_csv: str
    summary_markdown: str
    paper_table_csv: str
    prediction_content_sha256: Sha256
    metrics_content_sha256: Sha256


class EvaluationRun(DomainModel):
    id: StableId
    configuration_id: StableId
    state: RunState
    run_type: Literal["deterministic_fixture_validation"]
    empirical_model_run: Literal[False]
    eligible_for_performance_claims: Literal[False]
    current_fda_operational_availability: Literal["not_operational"]
    systems: tuple[SystemName, ...]
    seed: int
    created_at: str
    updated_at: str
    metrics: tuple[MetricsReport, ...] = ()
    cases: tuple[CaseEvaluation, ...] = ()
    artifacts: EvaluationArtifacts | None = None
    error: str | None = None
