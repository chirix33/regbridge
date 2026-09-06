import re

from app.domain.enums import EdgeType, EnforcementMode, NodeType, ReviewStatus, VerificationBasis
from app.domain.models import AnalysisResult, DossierEvidence
from app.graph.models import GraphEdge, GraphNeighborhood, GraphNode
from app.rules.registry import APPROVED_M1_MAPPING

GRAPH_CONTRACT_CHANGE = (
    "Metadata is represented as occurrence-level dossier evidence which OBSERVES a normalized "
    "keyword; model findings CITE the occurrence and are ABOUT the observed keyword."
)

GRAPH_CONTRACT_DEVIATION = {
    "status": "approved_deviation",
    "approved_by": "author-01",
    "approved_design": (
        "discriminated occurrence-evidence union: DOCUMENT_EVIDENCE, METADATA_EVIDENCE, "
        "and STRUCTURAL_EVIDENCE"
    ),
    "implementation": (
        "one DOSSIER_EVIDENCE occurrence node type with an evidence_kind discriminator"
    ),
    "implementation_assessment": "replaced_by_simpler_semantically_equivalent_representation",
    "edge_realization": (
        "MODEL_FINDING-CITES-DOSSIER_EVIDENCE; MODEL_FINDING-ABOUT-KEYWORD; "
        "DOSSIER_EVIDENCE-OBSERVES-KEYWORD"
    ),
    "rationale": (
        "The uniform occurrence node preserves exact raw value, owner, locator, provenance, "
        "request-local aliasing, occurrence citation, concept normalization, and Case A/B/C "
        "domain-range coverage without adding unused graph node subtypes during M3."
    ),
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "empty"


def _metadata_identity(evidence: DossierEvidence) -> tuple[str, str, str, str]:
    name, separator, raw_value = evidence.text.partition("=")
    if not separator or not name.strip():
        raise ValueError(f"metadata evidence {evidence.id} lacks an exact name=value occurrence")
    normalized_name = name.strip().casefold()
    normalized_value = raw_value.strip().casefold()
    keyword_id = f"keyword-{_slug(normalized_name)}-{_slug(normalized_value)}"
    return keyword_id, normalized_name, normalized_value, raw_value


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
        source_heading = result.source_artifact.source_heading
        target_heading = APPROVED_M1_MAPPING[source_heading]
        edges.extend(
            (
                GraphEdge(
                    id=f"edge-{source_heading.replace('.', '')}-removed-v40",
                    source=heading_id,
                    target=target_version_id,
                    type=EdgeType.REMOVED_IN,
                    label="removed in",
                    evidence_ids=("ev-ctoc-3211-3213-removed",),
                    review_status=ReviewStatus.SOURCE_VERIFIED,
                ),
                GraphEdge(
                    id=f"edge-{source_heading.replace('.', '')}-maps-321",
                    source=heading_id,
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
    observed_keyword_by_evidence: dict[str, str] = {}
    for evidence in result.evidence:
        if isinstance(evidence, DossierEvidence):
            evidence_node_id = f"dossier-{evidence.id}"
            properties = {
                "evidence_identity": "dossier_occurrence",
                "evidence_kind": evidence.kind,
                "raw_value": evidence.text,
                "owner": evidence.artifact_id,
                "locator": evidence.locator,
                "provenance": {
                    "evidence_id": evidence.id,
                    "file_sha256": evidence.file_sha256,
                    "extraction_method": evidence.extraction_method.value,
                },
            }
            if evidence.kind == "metadata":
                keyword_id, name, normalized_value, raw_value = _metadata_identity(evidence)
                properties["raw_value"] = raw_value
                properties["raw_record"] = evidence.text
                properties["normalized_keyword_id"] = keyword_id
                existing = nodes.get(keyword_id)
                keyword_label = f'{name}="{normalized_value}"'
                if existing is not None and existing.label != keyword_label:
                    raise ValueError(f"normalized keyword identifier collision: {keyword_id}")
                add(
                    GraphNode(
                        id=keyword_id,
                        type=NodeType.KEYWORD,
                        label=keyword_label,
                        properties={
                            "name": name,
                            "normalized_value": normalized_value,
                            "ontology_role": "normalized_keyword_concept",
                        },
                    )
                )
                observed_keyword_by_evidence[evidence.id] = keyword_id
                edges.append(
                    GraphEdge(
                        id=f"edge-{artifact_id}-{evidence.id}",
                        source=artifact_id,
                        target=keyword_id,
                        type=EdgeType.HAS_KEYWORD,
                        label="has parsed keyword",
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"edge-{evidence.id}-observes-{keyword_id}",
                        source=evidence_node_id,
                        target=keyword_id,
                        type=EdgeType.OBSERVES,
                        label="observes normalized keyword",
                        evidence_ids=(evidence.id,),
                        verification_basis=VerificationBasis.MECHANICAL_DERIVATION,
                    )
                )
            add(
                GraphNode(
                    id=evidence_node_id,
                    type=NodeType.DOSSIER_EVIDENCE,
                    label=evidence.locator,
                    properties=properties,
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
        finding_about_targets: set[tuple[str, str]] = set()
        for evidence_id in finding.evidence_ids:
            cited_evidence = next(
                (item for item in result.evidence if item.id == evidence_id), None
            )
            if cited_evidence is None:
                raise ValueError(f"finding cites unknown evidence occurrence: {evidence_id}")
            target_id = (
                f"dossier-{evidence_id}"
                if isinstance(cited_evidence, DossierEvidence)
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
            if is_model and evidence_id in observed_keyword_by_evidence:
                keyword_id = observed_keyword_by_evidence[evidence_id]
                finding_about_targets.add((keyword_id, evidence_id))
        for keyword_id in sorted({item[0] for item in finding_about_targets}):
            about_evidence_ids = tuple(
                sorted(
                    evidence_id
                    for target, evidence_id in finding_about_targets
                    if target == keyword_id
                )
            )
            if is_model:
                edges.append(
                    GraphEdge(
                        id=f"edge-{finding.id}-about-{keyword_id}",
                        source=finding_node_id,
                        target=keyword_id,
                        type=EdgeType.ABOUT,
                        label="about normalized keyword",
                        evidence_ids=about_evidence_ids,
                        review_status=ReviewStatus.CANDIDATE,
                        verification_basis=finding.verification_basis,
                        enforcement_mode=EnforcementMode.DISABLED,
                    )
                )
        decision_edge_type = (
            EdgeType.QUALIFIES_DECISION
            if is_model and result.decision_basis == "deterministic_hard_rule"
            else EdgeType.TRIGGERS_DECISION
        )
        edges.append(
            GraphEdge(
                id=f"edge-{finding.id}-decision",
                source=finding_node_id,
                target=decision_id,
                type=decision_edge_type,
                label=(
                    "qualifies hard structural decision"
                    if decision_edge_type == EdgeType.QUALIFIES_DECISION
                    else "contributes to synthesized decision"
                ),
            )
        )
        if not (is_model and result.decision_basis == "deterministic_hard_rule"):
            edges.append(
                GraphEdge(
                    id=f"edge-{finding.id}-repair",
                    source=finding_node_id,
                    target=repair_id,
                    type=EdgeType.REQUIRES_REPAIR,
                    label="informs next action",
                )
            )
    if result.model_run.status == "abstained":
        limitation_id = "limitation-semantic-inspection"
        add(
            GraphNode(
                id=limitation_id,
                type=NodeType.ANALYSIS_LIMITATION,
                label="Semantic inspection abstained",
                properties={
                    "component": "semantic-inspection",
                    "status": "abstained",
                    "reason_category": result.model_run.reason_category,
                    "prompt_version": result.model_run.prompt_template_version,
                    "request_digest": result.model_run.request_digest,
                },
            )
        )
        qualifies_hard_rule = result.decision_basis == "deterministic_hard_rule"
        edges.append(
            GraphEdge(
                id="edge-semantic-limitation-decision",
                source=limitation_id,
                target=decision_id,
                type=(
                    EdgeType.QUALIFIES_DECISION
                    if qualifies_hard_rule
                    else EdgeType.LEAVES_UNRESOLVED
                ),
                label=(
                    "qualifies hard structural decision"
                    if qualifies_hard_rule
                    else "leaves semantic eligibility unresolved"
                ),
            )
        )
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
