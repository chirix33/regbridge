from typing import Literal

from pydantic import Field, model_validator

from app.domain.enums import (
    ApplicationType,
    Authority,
    Bindingness,
    Center,
    Decision,
    EnforcementMode,
    ReviewDecision,
    ReviewStatus,
    ScenarioMode,
    Severity,
    StandardVersion,
    VerificationBasis,
)
from app.domain.models import DomainModel, ReviewEvent, StableId


class RuleScope(DomainModel):
    authority: Authority
    center: Center
    application_types: tuple[ApplicationType, ...] = Field(min_length=1)
    source_standard: StandardVersion
    target_standard: StandardVersion


class HeadingRule(DomainModel):
    id: StableId
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool = False
    scenario_mode: ScenarioMode
    scope: RuleScope
    explicit_heading_mapping: dict[str, str] = Field(min_length=1)
    verified_available_target_headings: tuple[str, ...] = Field(min_length=1)
    decision: Decision
    severity: Severity
    repair_type: StableId
    repair_description: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = Field(min_length=1)
    review_event: ReviewEvent

    @model_validator(mode="after")
    def validate_governance(self) -> "HeadingRule":
        if self.expert_validated and not self.review_event.expert_validated:
            raise ValueError("expert validation requires a qualified external review event")
        if self.enforcement_mode == EnforcementMode.HARD:
            if self.review_status != ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO:
                raise ValueError("hard rules must be author_adjudicated_for_demo")
            if self.verification_basis not in {
                VerificationBasis.DIRECT_STANDARD_ENCODING,
                VerificationBasis.MECHANICAL_DERIVATION,
            }:
                raise ValueError("hard rules require a direct or mechanical verification basis")
            if self.review_event.decision != ReviewDecision.ACCEPTED:
                raise ValueError("hard rules require an accepted author-review event")
        if (
            self.verification_basis == VerificationBasis.AUTHOR_INTERPRETATION
            and self.enforcement_mode != EnforcementMode.ADVISORY
        ):
            raise ValueError("author interpretations must be advisory")
        if (
            self.verification_basis == VerificationBasis.SEMANTIC_INFERENCE
            and self.enforcement_mode != EnforcementMode.SEMANTIC_SIGNAL
        ):
            raise ValueError("semantic inference must be a semantic_signal")
        return self


class MetadataRule(DomainModel):
    id: StableId
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    bindingness: Bindingness
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool = False
    scenario_mode: ScenarioMode
    scope: RuleScope
    predicate_type: Literal[
        "discouraged-manufacturer-value",
        "preserve-existing-lifecycle",
        "normalize-manufacturer-metadata",
        "hyperlink-relevance-gate",
    ]
    keyword_name: Literal["manufacturer"]
    normalized_value: Literal["all"]
    decision: Decision | None = None
    severity: Severity
    repair_type: StableId | None = None
    repair_description: str | None = None
    evidence_ids: tuple[StableId, ...] = Field(min_length=1)
    review_event: ReviewEvent

    @model_validator(mode="after")
    def validate_governance(self) -> "MetadataRule":
        if self.expert_validated:
            raise ValueError("M2 rules are not regulatory-expert validated")
        if self.review_status != ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO:
            raise ValueError("executable M2 rules must be author_adjudicated_for_demo")
        if self.enforcement_mode == EnforcementMode.HARD and self.verification_basis not in {
            VerificationBasis.DIRECT_STANDARD_ENCODING,
            VerificationBasis.MECHANICAL_DERIVATION,
        }:
            raise ValueError("hard M2 rules require direct or mechanical evidence")
        if (
            self.verification_basis == VerificationBasis.AUTHOR_INTERPRETATION
            and self.enforcement_mode != EnforcementMode.ADVISORY
        ):
            raise ValueError("author interpretations must be advisory")
        if (
            self.verification_basis == VerificationBasis.SEMANTIC_INFERENCE
            and self.enforcement_mode != EnforcementMode.SEMANTIC_SIGNAL
        ):
            raise ValueError("semantic inferences must be semantic_signal")
        if self.decision and (not self.repair_type or not self.repair_description):
            raise ValueError("decision rules require a fixed repair or next action")
        if self.review_event.decision != ReviewDecision.ACCEPTED:
            raise ValueError("M2 rules require an accepted author review event")
        return self
