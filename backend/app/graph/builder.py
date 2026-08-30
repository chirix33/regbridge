from app.domain.enums import EdgeType, EnforcementMode, NodeType, ReviewStatus
from app.domain.models import AnalysisResult, DossierEvidence
from app.graph.models import GraphEdge, GraphNeighborhood, GraphNode
from app.rules.registry import APPROVED_M1_MAPPING

_EDGE_DOMAINS: dict[EdgeType, tuple[set[NodeType], set[NodeType]]] = {
    EdgeType.LOCATED_UNDER: ({NodeType.ARTIFACT}, {NodeType.HEADING}),
    EdgeType.SUPPORTED_BY: ({NodeType.RULE}, {NodeType.EVIDENCE, NodeType.DOSSIER_EVIDENCE}),
    EdgeType.REQUIRES_REPAIR: ({NodeType.RULE, NodeType.MODEL_FINDING}, {NodeType.REPAIR}),
    EdgeType.TRIGGERS_DECISION: ({NodeType.RULE, NodeType.MODEL_FINDING}, {NodeType.DECISION}),
    EdgeType.HAS_KEYWORD: ({NodeType.ARTIFACT}, {NodeType.KEYWORD}),
    EdgeType.CITES: ({NodeType.MODEL_FINDING}, {NodeType.DOSSIER_EVIDENCE}),
    EdgeType.AVAILABLE_IN: ({NodeType.HEADING}, {NodeType.STANDARD_VERSION}),
    EdgeType.REMOVED_IN: ({NodeType.HEADING}, {NodeType.STANDARD_VERSION}),
    EdgeType.MAPS_TO: ({NodeType.HEADING}, {NodeType.HEADING}),
}


def build_neighborhood(result: AnalysisResult) -> GraphNeighborhood:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def add(node: GraphNode) -> None:
        nodes[node.id] = node

    artifact_id = result.source_artifact.id
    heading_id = f"heading-322-{result.source_artifact.source_heading.replace('.', '').lower()}"
    add(GraphNode(id=artifact_id, type=NodeType.ARTIFACT, label=result.source_artifact.title))
    add(
        GraphNode(
            id=heading_id,
            type=NodeType.HEADING,
            label=result.source_artifact.source_heading,
            version="3.2.2",
        )
    )
    edges.append(
        GraphEdge(
            id=f"edge-{artifact_id}-heading",
            source=artifact_id,
            target=heading_id,
            type=EdgeType.LOCATED_UNDER,
            label="parsed beneath",
        )
    )
    if any(rule_id.startswith("FDA-CDER-M1-") for rule_id in result.triggered_rule_ids):
        target_version_id = "version-ectd-40"
        target_heading_id = "heading-40-32s1"
        add(
            GraphNode(
                id=target_version_id,
                type=NodeType.STANDARD_VERSION,
                label="eCTD v4.0",
                version="4.0",
            )
        )
        add(
            GraphNode(
                id=target_heading_id,
                type=NodeType.HEADING,
                label="3.2.S.1 General information",
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
            )
        )
        for source_heading, target_heading in APPROVED_M1_MAPPING.items():
            source_id = f"heading-322-{source_heading.replace('.', '').lower()}"
            add(
                GraphNode(
                    id=source_id,
                    type=NodeType.HEADING,
                    label=source_heading,
                    version="3.2.2",
                    review_status=ReviewStatus.SOURCE_VERIFIED,
                )
            )
            edges.extend(
                (
                    GraphEdge(
                        id=f"edge-{source_heading.replace('.', '')}-removed-v40",
                        source=source_id,
                        target=target_version_id,
                        type=EdgeType.REMOVED_IN,
                        label="removed in",
                        evidence_ids=("ev-ctoc-3211-3213-removed",),
                        review_status=ReviewStatus.SOURCE_VERIFIED,
                    ),
                    GraphEdge(
                        id=f"edge-{source_heading.replace('.', '')}-maps-321",
                        source=source_id,
                        target=target_heading_id,
                        type=EdgeType.MAPS_TO,
                        label=f"explicitly maps to {target_heading}",
                        evidence_ids=(
                            "ev-ctoc-321-remains",
                            "ev-ctoc-3211-3213-removed",
                            "ev-tcg-replacement-context-same",
                            "ev-tcg-new-context-and-reuse",
                        ),
                        review_status=ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO,
                        enforcement_mode=EnforcementMode.HARD,
                    ),
                )
            )
    for evidence in result.evidence:
        if isinstance(evidence, DossierEvidence):
            node_type = (
                NodeType.KEYWORD if evidence.kind == "metadata" else NodeType.DOSSIER_EVIDENCE
            )
            evidence_node_id = f"dossier-{evidence.id}"
            add(GraphNode(id=evidence_node_id, type=node_type, label=evidence.locator))
            if evidence.kind == "metadata":
                edges.append(
                    GraphEdge(
                        id=f"edge-{artifact_id}-{evidence.id}",
                        source=artifact_id,
                        target=evidence_node_id,
                        type=EdgeType.HAS_KEYWORD,
                        label="has parsed keyword",
                    )
                )
        else:
            evidence_node_id = f"evidence-{evidence.id}"
            add(
                GraphNode(
                    id=evidence_node_id,
                    type=NodeType.EVIDENCE,
                    label=evidence.locator,
                    review_status=evidence.review_status,
                )
            )

    decision_id = f"decision-{result.decision.value.lower()}"
    repair_id = f"repair-{result.repair.type}"
    add(GraphNode(id=decision_id, type=NodeType.DECISION, label=result.decision.value))
    add(GraphNode(id=repair_id, type=NodeType.REPAIR, label=result.repair.description))
    for finding in result.findings:
        finding_node_id = f"finding-{finding.id}"
        is_model = finding.source.value == "model_assisted"
        finding_type = NodeType.MODEL_FINDING if is_model else NodeType.RULE
        add(
            GraphNode(
                id=finding_node_id,
                type=finding_type,
                label=finding.rationale,
                review_status=(
                    ReviewStatus.CANDIDATE if is_model else ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO
                ),
            )
        )
        for evidence_id in finding.evidence_ids:
            evidence = next(item for item in result.evidence if item.id == evidence_id)
            target_id = (
                f"dossier-{evidence_id}"
                if isinstance(evidence, DossierEvidence)
                else f"evidence-{evidence_id}"
            )
            edge_type = EdgeType.CITES if is_model else EdgeType.SUPPORTED_BY
            edges.append(
                GraphEdge(
                    id=f"edge-{finding.id}-{evidence_id}",
                    source=finding_node_id,
                    target=target_id,
                    type=edge_type,
                    label="cites" if is_model else "supported by",
                    evidence_ids=(evidence_id,),
                    review_status=(
                        ReviewStatus.CANDIDATE
                        if is_model
                        else ReviewStatus.AUTHOR_ADJUDICATED_FOR_DEMO
                    ),
                    verification_basis=finding.verification_basis,
                    enforcement_mode=(
                        EnforcementMode.DISABLED if is_model else finding.enforcement_mode
                    ),
                )
            )
        edges.extend(
            (
                GraphEdge(
                    id=f"edge-{finding.id}-decision",
                    source=finding_node_id,
                    target=decision_id,
                    type=EdgeType.TRIGGERS_DECISION,
                    label="visible in synthesized decision",
                ),
                GraphEdge(
                    id=f"edge-{finding.id}-repair",
                    source=finding_node_id,
                    target=repair_id,
                    type=EdgeType.REQUIRES_REPAIR,
                    label="informs next action",
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
    ordered_edges = tuple(sorted(edges, key=lambda item: item.id))
    return GraphNeighborhood(
        analysis_id=result.id,
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=ordered_edges,
        text_alternative=(
            tuple(f"{edge.source} {edge.label} {edge.target}." for edge in ordered_edges)
            or (f"{artifact_id} has no material graph findings.",)
        ),
    )
