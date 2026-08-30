from app.domain.enums import (
    EdgeType,
    EnforcementMode,
    NodeType,
    ReviewStatus,
    VerificationBasis,
)
from app.domain.models import AnalysisResult
from app.graph.models import GraphEdge, GraphNeighborhood, GraphNode
from app.rules.models import HeadingRule

_EDGE_DOMAINS: dict[EdgeType, tuple[set[NodeType], set[NodeType]]] = {
    EdgeType.LOCATED_UNDER: ({NodeType.ARTIFACT}, {NodeType.HEADING}),
    EdgeType.AVAILABLE_IN: ({NodeType.HEADING}, {NodeType.STANDARD_VERSION}),
    EdgeType.REMOVED_IN: ({NodeType.HEADING}, {NodeType.STANDARD_VERSION}),
    EdgeType.MAPS_TO: ({NodeType.HEADING}, {NodeType.HEADING}),
    EdgeType.SUPPORTED_BY: ({NodeType.RULE}, {NodeType.EVIDENCE}),
    EdgeType.REQUIRES_REPAIR: ({NodeType.RULE}, {NodeType.REPAIR}),
    EdgeType.TRIGGERS_DECISION: ({NodeType.RULE}, {NodeType.DECISION}),
}


def _heading_id(version: str, heading: str) -> str:
    return f"heading-{version.replace('.', '')}-{heading.replace('.', '').lower()}"


def build_neighborhood(result: AnalysisResult, rule: HeadingRule) -> GraphNeighborhood:
    source_version_id = "version-ectd-322"
    target_version_id = "version-ectd-40"
    artifact_id = result.source_artifact.id
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def add_node(node: GraphNode) -> None:
        nodes[node.id] = node

    add_node(GraphNode(id=artifact_id, type=NodeType.ARTIFACT, label=result.source_artifact.title))
    add_node(
        GraphNode(
            id=source_version_id,
            type=NodeType.STANDARD_VERSION,
            label="eCTD v3.2.2",
            version="3.2.2",
        )
    )
    add_node(
        GraphNode(
            id=target_version_id, type=NodeType.STANDARD_VERSION, label="eCTD v4.0", version="4.0"
        )
    )
    target_heading = rule.verified_available_target_headings[0]
    target_heading_id = _heading_id("40", target_heading)
    add_node(
        GraphNode(
            id=target_heading_id,
            type=NodeType.HEADING,
            label=f"{target_heading} General information",
            version="4.0",
            review_status=ReviewStatus.SOURCE_VERIFIED,
        )
    )
    edges.append(
        GraphEdge(
            id="edge-321-available-v40",
            source=target_heading_id,
            target=target_version_id,
            type=EdgeType.AVAILABLE_IN,
            label="available in",
            evidence_ids=("ev-ctoc-321-remains",),
            review_status=ReviewStatus.SOURCE_VERIFIED,
            verification_basis=VerificationBasis.DIRECT_STANDARD_ENCODING,
        )
    )
    for source_heading, mapped_heading in sorted(rule.explicit_heading_mapping.items()):
        source_heading_id = _heading_id("322", source_heading)
        add_node(
            GraphNode(
                id=source_heading_id,
                type=NodeType.HEADING,
                label=source_heading,
                version="3.2.2",
                review_status=ReviewStatus.SOURCE_VERIFIED,
            )
        )
        edges.extend(
            (
                GraphEdge(
                    id=f"edge-{source_heading.replace('.', '').lower()}-removed-v40",
                    source=source_heading_id,
                    target=target_version_id,
                    type=EdgeType.REMOVED_IN,
                    label="removed in",
                    evidence_ids=("ev-ctoc-3211-3213-removed",),
                    review_status=ReviewStatus.SOURCE_VERIFIED,
                    verification_basis=VerificationBasis.DIRECT_STANDARD_ENCODING,
                ),
                GraphEdge(
                    id=f"edge-{source_heading.replace('.', '').lower()}-maps-321",
                    source=source_heading_id,
                    target=_heading_id("40", mapped_heading),
                    type=EdgeType.MAPS_TO,
                    label="explicitly maps to",
                    evidence_ids=rule.evidence_ids,
                    review_status=ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO,
                    verification_basis=VerificationBasis.MECHANICAL_DERIVATION,
                    enforcement_mode=EnforcementMode.HARD,
                ),
            )
        )

    analyzed_heading = result.source_artifact.source_heading
    analyzed_heading_id = _heading_id("322", analyzed_heading)
    if analyzed_heading_id not in nodes:
        add_node(
            GraphNode(
                id=analyzed_heading_id,
                type=NodeType.HEADING,
                label=analyzed_heading,
                version="3.2.2",
            )
        )
    edges.append(
        GraphEdge(
            id=f"edge-{artifact_id}-located",
            source=artifact_id,
            target=analyzed_heading_id,
            type=EdgeType.LOCATED_UNDER,
            label="parsed beneath",
        )
    )

    rule_node_id = f"rule-{rule.id}"
    add_node(
        GraphNode(
            id=rule_node_id,
            type=NodeType.RULE,
            label=(
                f"Prospective rule (FDA status: {result.operational_status.value}): {rule.title}"
            ),
            version=rule.version,
            review_status=rule.review_status,
        )
    )
    for evidence in result.evidence:
        evidence_node_id = f"evidence-{evidence.id}"
        add_node(
            GraphNode(
                id=evidence_node_id,
                type=NodeType.EVIDENCE,
                label=evidence.locator,
                review_status=evidence.review_status,
            )
        )
        if evidence.id in rule.evidence_ids:
            edges.append(
                GraphEdge(
                    id=f"edge-rule-evidence-{evidence.id}",
                    source=rule_node_id,
                    target=evidence_node_id,
                    type=EdgeType.SUPPORTED_BY,
                    label="supported by",
                    evidence_ids=(evidence.id,),
                    review_status=rule.review_status,
                    verification_basis=rule.verification_basis,
                )
            )
    if rule.id in result.triggered_rule_ids:
        repair_id = f"repair-{result.repair.type}"
        decision_id = f"decision-{result.decision.value.lower()}"
        add_node(GraphNode(id=repair_id, type=NodeType.REPAIR, label=result.repair.description))
        add_node(GraphNode(id=decision_id, type=NodeType.DECISION, label=result.decision.value))
        edges.extend(
            (
                GraphEdge(
                    id="edge-rule-repair",
                    source=rule_node_id,
                    target=repair_id,
                    type=EdgeType.REQUIRES_REPAIR,
                    label="requires repair",
                    evidence_ids=rule.evidence_ids,
                    review_status=rule.review_status,
                    verification_basis=rule.verification_basis,
                    enforcement_mode=rule.enforcement_mode,
                ),
                GraphEdge(
                    id="edge-rule-decision",
                    source=rule_node_id,
                    target=decision_id,
                    type=EdgeType.TRIGGERS_DECISION,
                    label="supports decision",
                    evidence_ids=rule.evidence_ids,
                    review_status=rule.review_status,
                    verification_basis=rule.verification_basis,
                    enforcement_mode=rule.enforcement_mode,
                ),
            )
        )

    edge_ids: set[str] = set()
    for edge in edges:
        source_types, target_types = _EDGE_DOMAINS[edge.type]
        if (
            nodes[edge.source].type not in source_types
            or nodes[edge.target].type not in target_types
        ):
            raise ValueError(f"invalid graph domain/range for edge {edge.id}")
        if edge.id in edge_ids:
            raise ValueError("graph edge identifiers must be unique")
        edge_ids.add(edge.id)

    ordered_nodes = tuple(nodes[node_id] for node_id in sorted(nodes))
    ordered_edges = tuple(sorted(edges, key=lambda edge: edge.id))
    text = tuple(f"{edge.source} {edge.label} {edge.target}." for edge in ordered_edges)
    return GraphNeighborhood(
        analysis_id=result.id,
        nodes=ordered_nodes,
        edges=ordered_edges,
        text_alternative=text,
    )
