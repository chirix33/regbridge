from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.domain.enums import Decision, OperationalStatus, Severity
from app.domain.models import AnalysisResult, DomainModel, Sha256, StableId, TargetContext
from app.domain.vocabulary import RuntimeActionCode
from app.graph.models import GraphNeighborhood
from app.parsers.models import ApplicationInventory

ModelAvailability = Literal["available", "coming_soon", "misconfigured", "disabled"]
ProductRunState = Literal["queued", "running", "completed", "partial_failed", "failed"]


class ModelProfile(DomainModel):
    model_id: StableId
    display_name: str
    subtitle: str | None = None
    availability: ModelAvailability
    disabled_reason: str | None = None
    adapter_type: Literal["responses", "chat_completions"]
    execution_mode: Literal["live", "fixture", "disabled"]
    actual_adapter_type: Literal["responses", "chat_completions", "fixture"] | None = None
    configured_model_name: str | None = None
    structured_output_capability: Literal["validated", "unvalidated"]
    reasoning_capability: bool
    configuration_digest: Sha256
    network_required: bool

    @model_validator(mode="after")
    def validate_execution_disclosure(self) -> ModelProfile:
        if self.availability == "available" and self.actual_adapter_type is None:
            raise ValueError("available model profiles require an actual adapter")
        if self.execution_mode == "live" and self.availability == "available":
            if self.actual_adapter_type != "responses" or not self.network_required:
                raise ValueError("live GPT execution requires the Responses adapter and network")
        if self.execution_mode == "fixture" and self.availability == "available":
            if self.actual_adapter_type != "fixture" or self.network_required:
                raise ValueError("fixture execution must use the network-free fixture adapter")
        if self.execution_mode == "disabled" and self.availability == "available":
            raise ValueError("disabled execution cannot expose an available model")
        return self


class ModelCatalog(DomainModel):
    default_model_id: StableId
    models: tuple[ModelProfile, ...]


class ModelExecutionRecord(DomainModel):
    model_profile_id: StableId | Literal["model-free"]
    requested_model_name: str | None = None
    provider_reported_model_name: str | None = None
    adapter_type: Literal["responses", "chat_completions", "fixture", "model-free"]
    execution_mode: Literal["live", "fixture", "disabled"]
    configuration_digest: Sha256
    prompt_version: str
    request_digest: Sha256 | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    attempt_count: int = Field(default=1, ge=0, le=3)
    retry_causes: tuple[str, ...] = ()
    status: Literal["completed", "abstained", "failed", "not_applicable"]
    reason_category: str | None = None
    status_detail: str | None = Field(default=None, min_length=1, max_length=240)
    failure: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ModelExecutionRecord:
        if self.status == "abstained" and (
            self.reason_category is None or self.status_detail is None
        ):
            raise ValueError("abstained executions require a bounded reason")
        if self.status == "failed" and not self.failure:
            raise ValueError("failed executions require a redacted failure category")
        if self.status != "failed" and self.failure is not None:
            raise ValueError("only failed executions may carry failure")
        return self


class DossierAnalysisRequest(DomainModel):
    inventory_id: StableId
    model_id: StableId
    target_context: TargetContext
    leaf_ids: tuple[StableId, ...] | None = None


class DossierLeafFailure(DomainModel):
    leaf_id: StableId
    stage: str
    cause: str
    failure_category: Literal[
        "transport_or_provider_failure",
        "invalid_structured_output",
        "graph_failure",
        "persistence_failure",
        "analysis_failure",
    ] = "analysis_failure"
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
    pipeline_failure_count: int
    model_abstention_count: int
    skipped_count: int
    decision_counts: dict[str, int]
    severity_counts: dict[str, int]
    human_approval_count: int
    parser_warning_count: int
    policy_coverage_counts: dict[str, int]
    model_profile_id: StableId
    model_configuration_digest: Sha256

    @model_validator(mode="after")
    def validate_failure_compatibility(self) -> DossierAnalysisSummary:
        if self.failed_count != self.pipeline_failure_count:
            raise ValueError("failed_count must remain the pipeline-failure compatibility alias")
        return self


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

    @model_validator(mode="after")
    def validate_publication_boundary(self) -> DossierAnalysisRun:
        if any(item.model.status == "failed" for item in self.results):
            raise ValueError("terminally failed leaves cannot be published as decision results")
        if self.summary is not None and self.summary.analyzed_count != len(self.results):
            raise ValueError("analyzed count must equal published decision results")
        return self


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
    action: RuntimeActionCode | None = None
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
