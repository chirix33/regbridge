from typing import Any

from pydantic import Field, model_validator

from app.domain.enums import EdgeType, EnforcementMode, NodeType, ReviewStatus, VerificationBasis
from app.domain.models import DomainModel, StableId

GRAPH_SCHEMA_VERSION = "2.0.0"

EDGE_DOMAINS: dict[EdgeType, tuple[frozenset[NodeType], frozenset[NodeType]]] = {
    EdgeType.LOCATED_UNDER: (frozenset({NodeType.ARTIFACT}), frozenset({NodeType.HEADING})),
    EdgeType.SUPPORTED_BY: (
        frozenset({NodeType.RULE}),
        frozenset({NodeType.EVIDENCE, NodeType.DOSSIER_EVIDENCE}),
    ),
    EdgeType.REQUIRES_REPAIR: (
        frozenset({NodeType.RULE, NodeType.MODEL_FINDING}),
        frozenset({NodeType.REPAIR}),
    ),
    EdgeType.TRIGGERS_DECISION: (
        frozenset({NodeType.RULE, NodeType.MODEL_FINDING}),
        frozenset({NodeType.DECISION}),
    ),
    EdgeType.HAS_KEYWORD: (frozenset({NodeType.ARTIFACT}), frozenset({NodeType.KEYWORD})),
    EdgeType.CITES: (
        frozenset({NodeType.MODEL_FINDING}),
        frozenset({NodeType.DOSSIER_EVIDENCE}),
    ),
    EdgeType.ABOUT: (
        frozenset({NodeType.MODEL_FINDING}),
        frozenset({NodeType.KEYWORD}),
    ),
    EdgeType.OBSERVES: (
        frozenset({NodeType.DOSSIER_EVIDENCE}),
        frozenset({NodeType.KEYWORD}),
    ),
    EdgeType.AVAILABLE_IN: (
        frozenset({NodeType.HEADING}),
        frozenset({NodeType.STANDARD_VERSION}),
    ),
    EdgeType.REMOVED_IN: (
        frozenset({NodeType.HEADING}),
        frozenset({NodeType.STANDARD_VERSION}),
    ),
    EdgeType.MAPS_TO: (frozenset({NodeType.HEADING}), frozenset({NodeType.HEADING})),
}


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
        nodes = {node.id: node for node in self.nodes}
        node_ids = set(nodes)
        if len(node_ids) != len(self.nodes):
            raise ValueError("graph node identifiers must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise ValueError("graph edges must reference known nodes")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("graph edge identifiers must be unique")
        for edge in self.edges:
            source_types, target_types = EDGE_DOMAINS[edge.type]
            if (
                nodes[edge.source].type not in source_types
                or nodes[edge.target].type not in target_types
            ):
                raise ValueError(f"invalid graph domain/range for edge {edge.id}")

        model_findings = {
            node.id for node in self.nodes if node.type == NodeType.MODEL_FINDING
        }
        for finding_id in model_findings:
            finding = nodes[finding_id]
            if finding.review_status != ReviewStatus.CANDIDATE or finding.expert_validated:
                raise ValueError("model findings must remain non-expert candidate assertions")
            cited = {
                edge.target for edge in self.edges
                if edge.type == EdgeType.CITES and edge.source == finding_id
            }
            about = {
                edge.target for edge in self.edges
                if edge.type == EdgeType.ABOUT and edge.source == finding_id
            }
            if about and not cited:
                raise ValueError("ABOUT requires occurrence-level CITES evidence")
            metadata_citations = {
                target for target in cited
                if nodes[target].properties.get("evidence_kind") == "metadata"
            }
            observed = {
                edge.target for edge in self.edges
                if edge.type == EdgeType.OBSERVES and edge.source in metadata_citations
            }
            if metadata_citations and about != observed:
                raise ValueError(
                    "ABOUT keyword must exactly agree with the keyword OBSERVED by cited "
                    "metadata evidence"
                )
            if about and not metadata_citations:
                raise ValueError("ABOUT requires cited metadata occurrence evidence")
        for edge in self.edges:
            if edge.type in {EdgeType.CITES, EdgeType.ABOUT} and (
                edge.review_status != ReviewStatus.CANDIDATE
                or edge.enforcement_mode != EnforcementMode.DISABLED
                or edge.expert_validated
            ):
                raise ValueError("model-originated graph edges must remain disabled candidates")
        return self
