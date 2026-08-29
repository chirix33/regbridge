from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.api.contracts import (
    HealthResponse,
    ScopeResponse,
    StandardSourceSummary,
    StandardsSnapshotResponse,
)
from app.config import Settings, get_settings
from app.domain.enums import ApplicationType, Authority, Center, StandardVersion
from app.domain.models import StandardsManifest
from app.standards.registry import StandardsRegistry

RESEARCH_QUESTION = (
    "Can a typed, version-aware regulatory graph plus executable constraints identify unsafe "
    "or ambiguous reuse of legacy FDA eCTD content more reliably and explainably than the "
    "planned comparison systems?"
)
DISCLAIMER = (
    "RegBridge is an FDA/CDER-scoped research prototype for risk analysis and decision support. "
    "It is not FDA-certified, does not provide regulatory advice, and does not predict or "
    "guarantee filing or application acceptance. Use public, synthetic, or deliberately "
    "de-identified materials only."
)

router = APIRouter()


def get_manifest() -> StandardsManifest:
    return StandardsRegistry().load()


SettingsDependency = Annotated[Settings, Depends(get_settings)]
ManifestDependency = Annotated[StandardsManifest, Depends(get_manifest)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(
    settings: SettingsDependency,
    manifest: ManifestDependency,
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="regbridge",
        version=__version__,
        model_mode=settings.llm_mode,
        standards_snapshot_id=manifest.snapshot_id,
    )


@router.get("/api/v1/config/scope", response_model=ScopeResponse, tags=["configuration"])
def scope(
    settings: SettingsDependency,
    manifest: ManifestDependency,
) -> ScopeResponse:
    return ScopeResponse(
        product_name="RegBridge",
        product_type="research prototype",
        research_question=RESEARCH_QUESTION,
        authority=Authority.FDA,
        center=Center.CDER,
        supported_application_types=(ApplicationType.NDA,),
        source_standards=(StandardVersion.ECTD_3_2_2,),
        target_standards=(StandardVersion.ECTD_4_0,),
        standards_snapshot_id=manifest.snapshot_id,
        model_mode=settings.llm_mode,
        network_required=settings.llm_mode.value == "live",
        available_features=("scope", "standards-registry", "offline-model-fixtures"),
        planned_archetypes=(
            "unavailable-heading",
            "legacy-metadata-tension",
            "stale-content-or-hyperlink",
        ),
        disclaimer=DISCLAIMER,
        limitations=(
            "FDA/CDER and the reviewed demonstration snapshot only.",
            "No submission-package generation, acceptance prediction, or regulatory advice.",
            "M0 exposes contracts and provenance; artifact analysis begins in M1.",
        ),
    )


@router.get(
    "/api/v1/standards/snapshots",
    response_model=StandardsSnapshotResponse,
    tags=["standards"],
)
def standards_snapshots(
    manifest: ManifestDependency,
) -> StandardsSnapshotResponse:
    return StandardsSnapshotResponse(
        snapshot_id=manifest.snapshot_id,
        manifest_version=manifest.manifest_version,
        description=manifest.description,
        sources=tuple(
            StandardSourceSummary(
                id=source.id,
                title=source.title,
                version=source.version,
                authority=source.authority,
                center=source.center,
                source_url=source.source_url,
                sha256=source.sha256,
                review_status=source.review_status,
                reviewer_note=source.reviewer_note,
            )
            for source in manifest.sources
        ),
    )
