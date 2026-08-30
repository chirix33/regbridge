from typing import Any

from pydantic import Field, model_validator

from app.domain.enums import EdgeType, EnforcementMode, NodeType, ReviewStatus, VerificationBasis
from app.domain.models import DomainModel, StableId


class GraphNode(DomainModel):
    id: StableId
    type: NodeType
    label: str = Field(min_length=1)
    version: str | None = None
    review_status: ReviewStatus | None = None
    expert_validated: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(DomainModel):
    id: StableId
    source: StableId
    target: StableId
    type: EdgeType
    label: str = Field(min_length=1)
    evidence_ids: tuple[StableId, ...] = ()
    review_status: ReviewStatus | None = None
    verification_basis: VerificationBasis | None = None
    enforcement_mode: EnforcementMode = EnforcementMode.DISABLED
    expert_validated: bool = False

    @model_validator(mode="after")
    def validate_governance(self) -> "GraphEdge":
        if self.expert_validated:
            raise ValueError("M1 graph assertions are not regulatory-expert validated")
        if (
            self.review_status == ReviewStatus.CANDIDATE
            and self.enforcement_mode != EnforcementMode.DISABLED
        ):
            raise ValueError("candidate graph assertions cannot be enforced")
        return self


class GraphNeighborhood(DomainModel):
    analysis_id: StableId
    nodes: tuple[GraphNode, ...] = Field(min_length=1)
    edges: tuple[GraphEdge, ...]
    text_alternative: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> "GraphNeighborhood":
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("graph node identifiers must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("graph edges must reference known nodes")
        return self
