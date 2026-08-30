from pathlib import Path

import yaml
from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.config import REPOSITORY_ROOT
from app.domain.enums import (
    EnforcementMode,
    OperationalStatus,
    ReviewStatus,
    VerificationBasis,
)
from app.domain.models import DomainModel, StableId


class OperationalAvailability(DomainModel):
    record_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: OperationalStatus
    capability: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    source_url: HttpUrl
    recorded_at: AwareDatetime
    recorded_by: StableId
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool = False
    rationale: str = Field(min_length=1)
    unresolved_assumptions: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_m1_record(self) -> "OperationalAvailability":
        if self.status != OperationalStatus.NOT_OPERATIONAL:
            raise ValueError("the M1 operational record must remain not_operational")
        if self.review_status != ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO:
            raise ValueError("operational status requires the recorded author adjudication")
        if self.enforcement_mode != EnforcementMode.DISABLED:
            raise ValueError("operational status is a mode guard, not an executable rule")
        if self.expert_validated:
            raise ValueError("the M1 operational record is not regulatory-expert validated")
        return self


class OperationalStatusRegistry:
    def __init__(self, record_path: Path | None = None) -> None:
        self.record_path = (
            record_path or REPOSITORY_ROOT / "data" / "standards" / "operational-status.yaml"
        )

    def load(self) -> OperationalAvailability:
        payload = yaml.safe_load(self.record_path.read_text(encoding="utf-8"))
        return OperationalAvailability.model_validate(payload)
