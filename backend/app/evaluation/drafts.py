from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from app.config import REPOSITORY_ROOT
from app.domain.enums import Decision, ReviewStatus, Severity
from app.domain.models import DomainModel, StableId


class BenchmarkDraft(DomainModel):
    case_id: StableId
    archetype: Literal[
        "unavailable-heading",
        "legacy-metadata-tension",
        "stale-content-or-hyperlink",
    ]
    input_fixture: StableId
    target_context_id: StableId
    mutation_spec: str = Field(min_length=1)
    reference_decision: Decision | None = None
    reference_severity: Severity | None = None
    required_rule_ids: tuple[StableId, ...] = ()
    acceptable_evidence_ids: tuple[StableId, ...] = ()
    required_repair_type: StableId | None = None
    human_review_required: bool | None = None
    reference_rationale: str | None = None
    adjudication_status: ReviewStatus
    expert_validated: bool = False
    reviewer_id: StableId | None = None
    split: Literal["unassigned"] = "unassigned"
    provenance: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_draft_status(self) -> "BenchmarkDraft":
        if self.expert_validated:
            raise ValueError("M2 benchmark drafts are not expert validated")
        if self.adjudication_status == ReviewStatus.CANDIDATE and self.reference_decision:
            raise ValueError("candidate drafts must not carry a reference decision")
        if self.adjudication_status == ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO:
            required = (
                self.reference_decision,
                self.reference_severity,
                self.required_repair_type,
                self.reference_rationale,
                self.reviewer_id,
            )
            if any(value is None for value in required):
                raise ValueError("author-adjudicated draft requires a complete reference record")
        return self


class BenchmarkDraftSet(DomainModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    snapshot_id: StableId
    status: Literal["draft-unfrozen"]
    cases: tuple[BenchmarkDraft, ...] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_distribution(self) -> "BenchmarkDraftSet":
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark draft case identifiers must be unique")
        counts = {
            archetype: sum(item.archetype == archetype for item in self.cases)
            for archetype in (
                "unavailable-heading",
                "legacy-metadata-tension",
                "stale-content-or-hyperlink",
            )
        }
        if set(counts.values()) != {10}:
            raise ValueError("M2 requires exactly ten drafts per archetype")
        return self


def load_benchmark_drafts(path: Path | None = None) -> BenchmarkDraftSet:
    source = path or REPOSITORY_ROOT / "data" / "benchmark" / "draft-cases.yaml"
    return BenchmarkDraftSet.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))
