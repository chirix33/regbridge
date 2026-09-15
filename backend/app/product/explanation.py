"""Product-only evidence projection; never participates in analysis or evaluation."""

from __future__ import annotations

from typing import Literal

from app.domain.models import (
    AnalysisResult,
    DomainModel,
    DossierEvidence,
    EvidenceSpan,
    Finding,
    RuntimeRepairAction,
)
from app.standards.registry import StandardsRegistry, StandardsRegistryError


class SupportingSource(DomainModel):
    evidence_id: str
    source_id: str
    title: str
    version: str
    source_url: str
    sha256: str


class ProductExplanation(DomainModel):
    version: Literal["1.0.0"] = "1.0.0"
    findings: tuple[Finding, ...] | None = None
    repair: RuntimeRepairAction | None = None
    evidence: tuple[EvidenceSpan | DossierEvidence, ...] = ()
    sources: tuple[SupportingSource, ...] = ()
    uncertainty: tuple[str, ...] | None = None
    limitations: tuple[str, ...] = ()
    confidence: float | None = None


def explanation(
    *,
    evidence: tuple[EvidenceSpan | DossierEvidence, ...],
    analysis: AnalysisResult | None = None,
    confidence: float | None = None,
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
