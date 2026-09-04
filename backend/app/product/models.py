from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, Field

from app.domain.enums import Decision, OperationalStatus, Severity
from app.domain.models import AnalysisResult, DomainModel, Sha256, StableId, TargetContext
from app.domain.vocabulary import ActionCode
from app.graph.models import GraphNeighborhood
from app.parsers.models import ApplicationInventory

ModelAvailability = Literal["available", "coming_soon", "misconfigured"]
ProductRunState = Literal["queued", "running", "completed", "partial_failed", "failed"]


class ModelProfile(DomainModel):
    model_id: StableId
    display_name: str
    subtitle: str | None = None
    availability: ModelAvailability
    disabled_reason: str | None = None
    adapter_type: Literal["responses", "chat_completions"]
    configured_model_name: str | None = None
    structured_output_capability: Literal["validated", "unvalidated"]
    reasoning_capability: bool
    configuration_digest: Sha256
    network_required: bool


class ModelCatalog(DomainModel):
    default_model_id: StableId
    models: tuple[ModelProfile, ...]


class ModelExecutionRecord(DomainModel):
    model_profile_id: StableId | Literal["model-free"]
    requested_model_name: str | None = None
    provider_reported_model_name: str | None = None
    adapter_type: Literal["responses", "chat_completions", "fixture", "model-free"]
    configuration_digest: Sha256
    prompt_version: str
    request_digest: Sha256 | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    attempt_count: int = Field(default=1, ge=0, le=3)
    retry_causes: tuple[str, ...] = ()
    status: Literal["completed", "failed", "not_applicable"]
    failure: str | None = None


class DossierAnalysisRequest(DomainModel):
    inventory_id: StableId
    model_id: StableId
    target_context: TargetContext
    leaf_ids: tuple[StableId, ...] | None = None


class DossierLeafFailure(DomainModel):
    leaf_id: StableId
    stage: str
    cause: str
    retryable: bool = False


class DossierLeafResult(DomainModel):
    leaf_id: StableId
    analysis_ref: StableId
    analysis: AnalysisResult
    graph: GraphNeighborhood
    model: ModelExecutionRecord


class DossierAnalysisSummary(DomainModel):
    package_sha256: Sha256
    application_number: str | None = None
    submission_type: str | None = None
    applicant_name: str | None = None
    total_supported_leaves: int
    analyzed_count: int
    failed_count: int
    skipped_count: int
    decision_counts: dict[str, int]
    severity_counts: dict[str, int]
    human_approval_count: int
    parser_warning_count: int
    policy_coverage_counts: dict[str, int]
    model_profile_id: StableId
    model_configuration_digest: Sha256


class DossierAnalysisRun(DomainModel):
    run_id: StableId
    state: ProductRunState
    inventory_id: StableId
    input_profile_id: StableId
    selected_model: ModelProfile
    target_context: TargetContext
    execution_configuration_digest: Sha256
    requested_leaf_ids: tuple[StableId, ...]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    summary: DossierAnalysisSummary | None = None
    results: tuple[DossierLeafResult, ...] = ()
    failures: tuple[DossierLeafFailure, ...] = ()
    operational_status: Literal[OperationalStatus.NOT_OPERATIONAL] = (
        OperationalStatus.NOT_OPERATIONAL
    )
    expert_validated: Literal[False] = False
    capability_boundary: str


class ComparisonRequest(DomainModel):
    inventory_id: StableId
    model_id: StableId
    target_context: TargetContext
    leaf_ids: tuple[StableId, ...] | None = None


class RetrievalItem(DomainModel):
    alias: StableId
    evidence_id: StableId
    score: float
    rank: int


class ComparisonCell(DomainModel):
    leaf_id: StableId
    system: Literal["B0", "B1", "B2", "RegBridge"]
    package_sha256: Sha256
    selected_file_sha256: Sha256
    package_input_digest: Sha256
    model: ModelExecutionRecord
    decision: Decision | None = None
    severity: Severity | None = None
    action: ActionCode | None = None
    human_review_required: bool | None = None
    rationale: str | None = None
    evidence_ids: tuple[StableId, ...] = ()
    rule_ids: tuple[StableId, ...] = ()
    retrieval: tuple[RetrievalItem, ...] = ()
    graph: GraphNeighborhood | None = None
    trace: tuple[dict[str, Any], ...] = ()
    status: Literal["completed", "invalid_output", "failed"]
    failure: str | None = None


class ComparisonRun(DomainModel):
    comparison_id: StableId
    state: ProductRunState
    inventory_id: StableId
    input_profile_id: StableId
    selected_model: ModelProfile
    target_context: TargetContext
    execution_configuration_digest: Sha256
    requested_leaf_ids: tuple[StableId, ...]
    systems: tuple[Literal["B0", "B1", "B2", "RegBridge"], ...] = ("B0", "B1", "B2", "RegBridge")
    created_at: AwareDatetime
    updated_at: AwareDatetime
    results: tuple[ComparisonCell, ...] = ()
    failures: tuple[DossierLeafFailure, ...] = ()
    operational_status: Literal[OperationalStatus.NOT_OPERATIONAL] = (
        OperationalStatus.NOT_OPERATIONAL
    )
    expert_validated: Literal[False] = False
    benchmark_evaluation: Literal[False] = False


class InventoryEnvelope(DomainModel):
    inventory_id: StableId
    expires_at: AwareDatetime
    restart_persistence: Literal["none"] = "none"
    raw_zip_retained: Literal[False] = False
    inventory: ApplicationInventory
