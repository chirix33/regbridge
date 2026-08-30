from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    EnforcementMode,
    LlmMode,
    OperationalStatus,
    ReviewStatus,
    ScenarioMode,
    StandardVersion,
    VerificationBasis,
)
from app.domain.models import AnalysisResult, TargetContext
from app.graph.models import GraphNeighborhood
from app.parsers.models import FixtureSummary


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: Literal["regbridge"]
    version: str
    model_mode: LlmMode
    standards_snapshot_id: str


class ScopeResponse(ApiModel):
    product_name: Literal["RegBridge"]
    product_type: Literal["research prototype", "risk analyzer", "decision support"]
    research_question: str
    authority: Authority
    center: Center
    supported_application_types: tuple[ApplicationType, ...]
    source_standards: tuple[StandardVersion, ...]
    target_standards: tuple[StandardVersion, ...]
    standards_snapshot_id: str
    model_mode: LlmMode
    network_required: bool
    operational_status: OperationalStatus
    approved_research_scenario: ScenarioMode
    expert_validated: bool
    available_features: tuple[str, ...]
    planned_archetypes: tuple[str, ...]
    disclaimer: str
    limitations: tuple[str, ...]


class StandardSourceSummary(ApiModel):
    id: str
    title: str
    version: str
    authority: Authority
    center: Center
    source_url: HttpUrl
    sha256: str
    review_status: ReviewStatus
    verification_basis: VerificationBasis
    enforcement_mode: EnforcementMode
    expert_validated: bool
    reviewer_note: str


class StandardsSnapshotResponse(ApiModel):
    snapshot_id: str
    manifest_version: str
    description: str
    sources: tuple[StandardSourceSummary, ...]


class FixtureListResponse(ApiModel):
    fixtures: tuple[FixtureSummary, ...]


class AnalysisRequest(ApiModel):
    inventory_id: str
    leaf_id: str
    target_context: TargetContext


class AnalysisResponse(ApiModel):
    analysis: AnalysisResult


class GraphResponse(ApiModel):
    graph: GraphNeighborhood
