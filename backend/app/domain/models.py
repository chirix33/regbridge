from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.domain.enums import (
    ApplicationType,
    Authority,
    Bindingness,
    Center,
    Decision,
    EnforcementMode,
    ExtractionMethod,
    ManufacturerPartitioning,
    MetadataMigrationIntent,
    OperationalStatus,
    ReuseOperation,
    ReviewDecision,
    ReviewStatus,
    ScenarioMode,
    Severity,
    StandardVersion,
    TraceStepKind,
    VerificationBasis,
)

StableId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetContext(DomainModel):
    authority: Authority
    center: Center
    application_type: ApplicationType
    source_standard: StandardVersion
    target_standard: StandardVersion
    analysis_date: date
    reuse_operation: ReuseOperation
    standards_snapshot_id: StableId
    scenario_mode: ScenarioMode
    metadata_plan: "MetadataPlan | None" = None

    @model_validator(mode="after")
    def validate_version_transition(self) -> "TargetContext":
        if self.source_standard == self.target_standard:
            raise ValueError("source_standard and target_standard must differ")
        return self


class MetadataPlan(DomainModel):
    intent: MetadataMigrationIntent
    manufacturer_partitioning: ManufacturerPartitioning = ManufacturerPartitioning.UNKNOWN
    replacement_manufacturer_value: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_plan(self) -> "MetadataPlan":
        replacement = (
            " ".join(self.replacement_manufacturer_value.split())
            if self.replacement_manufacturer_value
            else None
        )
        if self.intent != MetadataMigrationIntent.NORMALIZE_METADATA and replacement:
            raise ValueError("replacement value is allowed only for normalize-metadata intent")
        if self.manufacturer_partitioning == ManufacturerPartitioning.REQUIRED:
            if self.intent == MetadataMigrationIntent.NORMALIZE_METADATA and not replacement:
                raise ValueError("required manufacturer partitioning needs an explicit value")
            if replacement and replacement.casefold() in {"all", "applicant", "not specified"}:
                raise ValueError("replacement must be a stable distinguishing value")
        if self.manufacturer_partitioning == ManufacturerPartitioning.UNNECESSARY and replacement:
            raise ValueError("unnecessary partitioning must omit the manufacturer keyword")
        return self


class SourceScope(DomainModel):
    application_types: tuple[ApplicationType, ...] = Field(min_length=1)
    source_standards: tuple[StandardVersion, ...] = Field(min_length=1)
    target_standards: tuple[StandardVersion, ...] = Field(min_length=1)
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "SourceScope":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from")
        return self


class RegulatorySource(DomainModel):
    id: StableId
    title: str = Field(min_length=1)
    authority: Authority
    jurisdiction: str = Field(min_length=2)
    issuing_organization: str = Field(min_length=2)
    center: Center
    version: str = Field(min_length=1)
    published_at: date | None = None
    effective_from: date | None = None
    source_url: HttpUrl
    retrieved_at: AwareDatetime
    local_path: Annotated[
        str,
        Field(pattern=r"^snapshots/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"),
    ]
    sha256: Sha256
    bindingness: Bindingness
    scope: SourceScope
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool = False
    review_events: tuple["ReviewEvent", ...] = Field(min_length=1)
    review_locator: str = Field(min_length=1)
    reviewer_note: str = Field(min_length=1)
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reviewed_source(self) -> "RegulatorySource":
        if self.review_status == ReviewStatus.CANDIDATE:
            raise ValueError("standards manifest entries must be source-verified or rejected")
        if self.enforcement_mode != EnforcementMode.DISABLED:
            raise ValueError("manifest entries do not independently enforce conclusions")
        if self.expert_validated and not any(
            event.expert_validated for event in self.review_events
        ):
            raise ValueError("expert validation requires a separately recorded external review")
        if self.review_status == ReviewStatus.SOURCE_VERIFIED and not any(
            event.decision == ReviewDecision.ACCEPTED for event in self.review_events
        ):
            raise ValueError("source-verified entries require an accepted author review event")
        return self


class ReviewEvent(DomainModel):
    id: StableId
    reviewer_id: StableId
    reviewer_role: str = Field(min_length=1)
    reviewed_at: AwareDatetime
    object_id: StableId
    object_version: str = Field(min_length=1)
    source_snapshot_id: StableId
    source_sha256: Sha256
    supporting_source_sha256s: tuple[Sha256, ...] = ()
    decision: ReviewDecision
    rationale: str = Field(min_length=1)
    unresolved_assumptions: tuple[str, ...] = ()
    independent_second_author_check: bool = False
    expert_validated: bool = False
    external_reviewer_qualification: str | None = None

    @model_validator(mode="after")
    def validate_expert_review(self) -> "ReviewEvent":
        if self.expert_validated and not self.external_reviewer_qualification:
            raise ValueError("expert validation requires a recorded external qualification")
        return self


class StandardsManifest(DomainModel):
    manifest_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    snapshot_id: StableId
    description: str = Field(min_length=1)
    sources: tuple[RegulatorySource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_sources(self) -> "StandardsManifest":
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("standards source identifiers must be unique")
        return self


class EvidenceSpan(DomainModel):
    id: StableId
    source_id: StableId
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1)
    bindingness: Bindingness
    applicability: SourceScope
    source_sha256: Sha256
    extraction_method: ExtractionMethod
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool = False
    review_events: tuple[ReviewEvent, ...] = ()

    @model_validator(mode="after")
    def validate_governance(self) -> "EvidenceSpan":
        if (
            self.review_status == ReviewStatus.CANDIDATE
            and self.enforcement_mode != EnforcementMode.DISABLED
        ):
            raise ValueError("candidate evidence cannot participate in enforcement")
        if self.expert_validated and not any(
            event.expert_validated for event in self.review_events
        ):
            raise ValueError("expert_validated requires qualified external review")
        if self.review_status == ReviewStatus.SOURCE_VERIFIED and not any(
            event.decision == ReviewDecision.ACCEPTED for event in self.review_events
        ):
            raise ValueError("source-verified evidence requires an accepted review event")
        return self


class DossierEvidence(DomainModel):
    id: StableId
    artifact_id: StableId
    kind: Annotated[str, Field(pattern=r"^(text|hyperlink|metadata)$")]
    locator: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    file_sha256: Sha256
    extraction_method: ExtractionMethod = ExtractionMethod.DETERMINISTIC


class SourceArtifact(DomainModel):
    id: StableId
    title: str = Field(min_length=1)
    source_standard: StandardVersion
    source_leaf_id: StableId
    source_heading: str = Field(pattern=r"^\d+(?:\.[A-Za-z0-9]+)+$")
    source_locator: str = Field(min_length=1)
    content_type: str = Field(pattern=r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
    file_sha256: Sha256


class RepairAction(DomainModel):
    type: StableId
    description: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()


class Finding(DomainModel):
    id: StableId
    rule_id: StableId | None = None
    severity: Severity
    rationale: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = Field(min_length=1)
    source: TraceStepKind
    verification_basis: VerificationBasis = VerificationBasis.SYNTHETIC_ASSUMPTION
    enforcement_mode: EnforcementMode = EnforcementMode.DISABLED


class TraceStep(DomainModel):
    sequence: int = Field(ge=1)
    kind: TraceStepKind
    component: StableId
    summary: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()
    occurred_at: AwareDatetime


class ModelRunRecord(DomainModel):
    mode: Annotated[str, Field(pattern=r"^(fixture|live|disabled)$")]
    status: Annotated[str, Field(pattern=r"^(completed|abstained|failed|not_applicable)$")]
    prompt_template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    model_name: str | None = None
    request_digest: Sha256 | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0)
    validation_error: str | None = Field(default=None, max_length=500)


class AnalysisResult(DomainModel):
    id: StableId
    source_artifact: SourceArtifact
    target_context: TargetContext
    operational_status: OperationalStatus
    scenario_disclosure: str = Field(min_length=1)
    expert_validated: bool = False
    decision: Decision
    severity: Severity
    triggered_rule_ids: tuple[StableId, ...]
    findings: tuple[Finding, ...]
    evidence: tuple[EvidenceSpan | DossierEvidence, ...]
    rationale: str = Field(min_length=1)
    repair: RepairAction
    confidence: float = Field(ge=0.0, le=1.0)
    unresolved_uncertainty: tuple[str, ...]
    human_approval_required: bool
    trace: tuple[TraceStep, ...] = Field(min_length=1)
    model_run: ModelRunRecord = ModelRunRecord(
        mode="disabled",
        status="not_applicable",
        prompt_template_version="1.0.0",
        model_name="contract-default",
        latency_ms=0,
    )

    @model_validator(mode="after")
    def validate_human_review_contract(self) -> "AnalysisResult":
        if self.expert_validated:
            raise ValueError("M1 results are not regulatory-expert validated")
        if self.decision == Decision.HUMAN_REGULATORY_REVIEW and not self.human_approval_required:
            raise ValueError("human review decisions require human approval")
        if self.decision == Decision.HUMAN_REGULATORY_REVIEW and not self.unresolved_uncertainty:
            raise ValueError("human review decisions require unresolved uncertainty")
        known_evidence_ids = {span.id for span in self.evidence}
        cited_evidence_ids = {
            evidence_id for finding in self.findings for evidence_id in finding.evidence_ids
        }
        cited_evidence_ids.update(self.repair.evidence_ids)
        cited_evidence_ids.update(
            evidence_id for step in self.trace for evidence_id in step.evidence_ids
        )
        if unsupported_evidence := cited_evidence_ids - known_evidence_ids:
            unsupported = ", ".join(sorted(unsupported_evidence))
            raise ValueError(f"analysis cites unknown evidence identifiers: {unsupported}")
        finding_rule_ids = {finding.rule_id for finding in self.findings if finding.rule_id}
        if finding_rule_ids != set(self.triggered_rule_ids):
            raise ValueError("triggered_rule_ids must match rule-backed findings")
        return self
