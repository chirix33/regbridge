"""Product-only evidence projection; never participates in analysis or evaluation."""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel

from app.domain.models import (
    AnalysisResult,
    DomainModel,
    DossierEvidence,
    EvidenceSpan,
    Finding,
    MetadataPlan,
    RuntimeRepairAction,
)
from app.llm.models import ModelCompletion, ModelRequest, SemanticRiskOutput
from app.llm.protocol import StructuredModel
from app.rules.models import HeadingRule, MetadataRule
from app.standards.registry import StandardsRegistry, StandardsRegistryError


class SupportingSource(DomainModel):
    evidence_id: str
    source_id: str
    title: str
    version: str
    source_url: str
    sha256: str


class PlacementObservation(DomainModel):
    finding_id: str
    source_heading: str
    target_heading: str
    evidence_ids: tuple[str, ...]


class SemanticTopic(DomainModel):
    finding_id: str
    category: str


class KeywordObservation(DomainModel):
    finding_id: str
    keyword_name: str


class ProductObservations(DomainModel):
    """Recorded input and validated finding topics, never newly inferred conclusions."""

    metadata_plan: MetadataPlan | None
    package_applicant_name: str | None = None
    placements: tuple[PlacementObservation, ...] = ()
    keywords: tuple[KeywordObservation, ...] = ()
    semantic_topics: tuple[SemanticTopic, ...] = ()


OutputT = TypeVar("OutputT", bound=BaseModel)


class ObservationCapture:
    """Observe the existing call without changing its request, output, or attribution."""

    def __init__(self, model: StructuredModel) -> None:
        self.model = model
        self.output: SemanticRiskOutput | None = None

    async def complete(
        self, request: ModelRequest, output_type: type[OutputT]
    ) -> ModelCompletion[OutputT]:
        completion = await self.model.complete(request, output_type)
        if isinstance(completion.output, SemanticRiskOutput):
            self.output = completion.output
        return completion


def observations(
    analysis: AnalysisResult,
    applicant: str | None,
    rules: tuple[HeadingRule, ...],
    semantic: SemanticRiskOutput | None,
    metadata_rules: tuple[MetadataRule, ...] = (),
) -> ProductObservations:
    placements = []
    for finding in analysis.findings:
        for rule in rules:
            target = rule.explicit_heading_mapping.get(analysis.source_artifact.source_heading)
            if (
                finding.rule_id == rule.id
                and target
                and set(rule.evidence_ids).issubset(finding.evidence_ids)
            ):
                placements.append(
                    PlacementObservation(
                        finding_id=finding.id,
                        source_heading=analysis.source_artifact.source_heading,
                        target_heading=target,
                        evidence_ids=finding.evidence_ids,
                    )
                )
    # Only categories belonging to findings actually accepted by the analyzer survive.
    accepted = {f.id: f for f in analysis.findings}
    topics = tuple(
        SemanticTopic(finding_id=f.id, category=f.category)
        for f in (semantic.findings if semantic else ())
        if f.id in accepted and f.evidence_ids == accepted[f.id].evidence_ids
    )
    return ProductObservations(
        metadata_plan=analysis.target_context.metadata_plan,
        package_applicant_name=applicant,
        placements=tuple(placements),
        semantic_topics=topics,
        keywords=tuple(
            KeywordObservation(finding_id=f.id, keyword_name=r.keyword_name)
            for f in analysis.findings
            for r in metadata_rules
            if f.rule_id == r.id and r.predicate_type != "hyperlink-relevance-gate"
        ),
    )


class ProductExplanation(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    findings: tuple[Finding, ...] | None = None
    repair: RuntimeRepairAction | None = None
    evidence: tuple[EvidenceSpan | DossierEvidence, ...] = ()
    sources: tuple[SupportingSource, ...] = ()
    uncertainty: tuple[str, ...] | None = None
    limitations: tuple[str, ...] = ()
    confidence: float | None = None
    observations: ProductObservations | None = None


def explanation(
    *,
    evidence: tuple[EvidenceSpan | DossierEvidence, ...],
    analysis: AnalysisResult | None = None,
    confidence: float | None = None,
    observed: ProductObservations | None = None,
) -> ProductExplanation:
    sources: list[SupportingSource] = []
    limitations: list[str] = []
    try:
        pinned = {source.id: source for source in StandardsRegistry().load().sources}
    except (StandardsRegistryError, ValueError, OSError):
        pinned = {}
        limitations.append(
            "Pinned source metadata could not be verified; recorded evidence remains available."
        )
    for item in evidence:
        if not isinstance(item, EvidenceSpan):
            continue
        source = pinned.get(item.source_id)
        if source is None or source.sha256 != item.source_sha256:
            limitations.append(f"Source identity/digest correspondence unavailable for {item.id}.")
            continue
        sources.append(
            SupportingSource(
                evidence_id=item.id,
                source_id=source.id,
                title=source.title,
                version=source.version,
                source_url=str(source.source_url),
                sha256=source.sha256,
            )
        )
    if analysis is None:
        limitations.append(
            "This direct approach supplies a native explanation and citations; "
            "structured findings, document repair description, and uncertainty are unavailable."
        )
    return ProductExplanation(
        observations=observed,
        findings=analysis.findings if analysis else None,
        repair=RuntimeRepairAction.model_validate(analysis.repair.model_dump())
        if analysis
        else None,
        evidence=evidence,
        sources=tuple(sources),
        uncertainty=analysis.unresolved_uncertainty if analysis else None,
        confidence=analysis.confidence if analysis else confidence,
        limitations=tuple(limitations),
    )
