from datetime import date
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.domain.enums import (
    ApplicationType,
    Authority,
    Bindingness,
    Center,
    Decision,
    ExtractionMethod,
    ReuseOperation,
    ReviewStatus,
    Severity,
    StandardVersion,
    TraceStepKind,
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

    @model_validator(mode="after")
    def validate_version_transition(self) -> "TargetContext":
        if self.source_standard == self.target_standard:
            raise ValueError("source_standard and target_standard must differ")
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
    review_locator: str = Field(min_length=1)
    reviewer_note: str = Field(min_length=1)
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reviewed_source(self) -> "RegulatorySource":
        if self.review_status == ReviewStatus.CANDIDATE:
            raise ValueError("standards manifest entries must be reviewed or explicitly rejected")
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


class SourceArtifact(DomainModel):
    id: StableId
    title: str = Field(min_length=1)
    source_standard: StandardVersion
    source_leaf_id: StableId
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


class TraceStep(DomainModel):
    sequence: int = Field(ge=1)
    kind: TraceStepKind
    component: StableId
    summary: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()
    occurred_at: AwareDatetime


class AnalysisResult(DomainModel):
    id: StableId
    source_artifact: SourceArtifact
    target_context: TargetContext
    decision: Decision
    severity: Severity
    triggered_rule_ids: tuple[StableId, ...]
    findings: tuple[Finding, ...]
    evidence: tuple[EvidenceSpan, ...]
    rationale: str = Field(min_length=1)
    repair: RepairAction
    confidence: float = Field(ge=0.0, le=1.0)
    unresolved_uncertainty: tuple[str, ...]
    human_approval_required: bool
    trace: tuple[TraceStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_human_review_contract(self) -> "AnalysisResult":
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
