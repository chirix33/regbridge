from typing import Literal

from pydantic import Field, JsonValue, model_validator

from app.domain.enums import Severity
from app.domain.models import DomainModel, EvidenceSpan, StableId


class ModelRequest(DomainModel):
    fixture_id: StableId
    task: str = Field(min_length=1)
    context: dict[str, JsonValue]
    evidence: tuple[EvidenceSpan, ...]
    prompt_template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class SemanticFinding(DomainModel):
    id: StableId
    basis: Literal["observation", "inference"]
    summary: str = Field(min_length=1)
    severity: Severity
    evidence_ids: tuple[StableId, ...] = Field(min_length=1)


class SemanticRiskOutput(DomainModel):
    fixture_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    abstained: bool
    abstain_reason: str | None
    findings: tuple[SemanticFinding, ...]
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_abstention(self) -> "SemanticRiskOutput":
        if self.abstained and not self.abstain_reason:
            raise ValueError("abstained model output requires abstain_reason")
        if not self.abstained and self.abstain_reason:
            raise ValueError("non-abstaining model output cannot include abstain_reason")
        if self.abstained and self.findings:
            raise ValueError("abstaining model output cannot include substantive findings")
        return self
