from dataclasses import dataclass
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from app.domain.enums import Severity
from app.domain.models import (
    DomainModel,
    DossierEvidence,
    EvidenceSpan,
    ModelRunRecord,
    StableId,
)


class ModelRequest(DomainModel):
    fixture_id: StableId
    task: str = Field(min_length=1)
    context: dict[str, JsonValue]
    evidence: tuple[EvidenceSpan | DossierEvidence, ...]
    prompt_template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")


class SemanticFinding(DomainModel):
    id: StableId
    basis: Literal["observation", "inference"]
    summary: str = Field(min_length=1)
    severity: Severity
    evidence_ids: tuple[StableId, ...] = Field(min_length=1)
    category: Literal[
        "obsolete_heading",
        "applicant_name_mismatch",
        "irrelevant_hyperlink",
        "broken_internal_destination",
        "benign_historical_reference",
        "ambiguous_reference",
    ] = "ambiguous_reference"


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
        if any(
            finding.severity in {Severity.BLOCKING, Severity.UNRESOLVED}
            for finding in self.findings
        ):
            raise ValueError("semantic findings may not claim blocking or unresolved severity")
        return self


@dataclass(frozen=True)
class ModelCompletion[ModelOutputT]:
    output: ModelOutputT
    run: ModelRunRecord

    def __getattr__(self, name: str) -> object:
        return getattr(self.output, name)
