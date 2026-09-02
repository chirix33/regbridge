from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status

from app import __version__
from app.analyzer.service import AnalysisService
from app.api.contracts import (
    AnalysisRequest,
    AnalysisResponse,
    BaselineRunRequest,
    BaselineRunResponse,
    DemoPresetsResponse,
    EvaluationCreateRequest,
    EvaluationResponse,
    FixtureListResponse,
    GraphResponse,
    HealthResponse,
    M4PresentationCasesResponse,
    M4PresentationResponse,
    ScopeResponse,
    StandardSourceSummary,
    StandardsSnapshotResponse,
)
from app.baselines.runner import BaselineRunner
from app.config import Settings, get_settings
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import StandardsManifest
from app.evaluation.benchmark import load_frozen_benchmark
from app.evaluation.jobs import EvaluationBusyError, EvaluationManager
from app.parsers.ectd322 import EctdParseError, FixtureCatalog, parse_zip
from app.parsers.models import ApplicationInventory
from app.presentation.repository import load_m4_snapshot
from app.standards.operational import OperationalStatusRegistry
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
    "de-identified materials only. The controlled M1/M2 scenarios and labels are author-"
    "adjudicated and have not been validated by a regulatory expert."
)

router = APIRouter()


def get_manifest() -> StandardsManifest:
    return StandardsRegistry().load()


SettingsDependency = Annotated[Settings, Depends(get_settings)]
ManifestDependency = Annotated[StandardsManifest, Depends(get_manifest)]

_inventories: dict[str, ApplicationInventory] = {}
_evaluation_manager = EvaluationManager()


@lru_cache
def get_analysis_service() -> AnalysisService:
    return AnalysisService()


AnalysisDependency = Annotated[AnalysisService, Depends(get_analysis_service)]


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
        operational_status=OperationalStatusRegistry().load().status,
        approved_research_scenario=ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        expert_validated=False,
        available_features=(
            "scope",
            "standards-registry",
            "secure-ectd-322-parser",
            "explicit-heading-rule",
            "graph-neighborhood",
            "metadata-lifecycle-rules",
            "pdf-evidence-extraction",
            "fixture-semantic-inspection",
            "openai-compatible-semantic-adapter",
            "shared-decision-synthesis",
            "frozen-benchmark",
            "baseline-runner",
            "deterministic-evaluation",
            "m4-presentation-snapshot",
            "m4-evaluation-dashboard",
            "m4-guided-demo",
        ),
        planned_archetypes=(
            "unavailable-heading",
            "legacy-metadata-tension",
            "stale-content-or-hyperlink",
        ),
        disclaimer=DISCLAIMER,
        limitations=(
            "FDA/CDER and the reviewed demonstration snapshot only.",
            "No submission-package generation, acceptance prediction, or regulatory advice.",
            "FDA forward compatibility is currently not operational.",
            "M1 and M2 are prospective controlled research scenarios, not operational guidance.",
            "Author-adjudicated labels and rules have not been validated by a regulatory expert.",
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
                verification_basis=source.verification_basis,
                enforcement_mode=source.enforcement_mode,
                expert_validated=source.expert_validated,
                reviewer_note=source.reviewer_note,
            )
            for source in manifest.sources
        ),
    )


@router.get("/api/v1/fixtures", response_model=FixtureListResponse, tags=["analysis"])
def fixtures() -> FixtureListResponse:
    return FixtureListResponse(fixtures=FixtureCatalog().list())


@router.post(
    "/api/v1/applications/parse",
    response_model=ApplicationInventory,
    tags=["analysis"],
)
async def parse_application(
    request: Request,
    fixture_id: Annotated[str | None, Query()] = None,
) -> ApplicationInventory:
    try:
        if fixture_id is not None:
            if await request.body():
                raise EctdParseError("provide a fixture_id or ZIP upload, not both")
            inventory = FixtureCatalog().parse(fixture_id)
        else:
            if request.headers.get("content-type", "").split(";", 1)[0] not in {
                "application/zip",
                "application/x-zip-compressed",
            }:
                raise EctdParseError("upload must use a ZIP MIME type")
            payload = await request.body()
            if not payload:
                raise EctdParseError("provide a controlled fixture_id or ZIP upload")
            inventory = parse_zip(payload)
    except EctdParseError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    _inventories[inventory.id] = inventory
    return inventory


@router.post("/api/v1/analyses", response_model=AnalysisResponse, tags=["analysis"])
async def create_analysis(
    request: AnalysisRequest,
    service: AnalysisDependency,
) -> AnalysisResponse:
    inventory = _inventories.get(request.inventory_id)
    if inventory is None:
        raise HTTPException(status_code=404, detail="parsed inventory not found")
    try:
        result = await service.analyze_async(inventory, request.leaf_id, request.target_context)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AnalysisResponse(analysis=result)


@router.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisResponse, tags=["analysis"])
def get_analysis(analysis_id: str, service: AnalysisDependency) -> AnalysisResponse:
    try:
        return AnalysisResponse(analysis=service.get(analysis_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/api/v1/analyses/{analysis_id}/graph", response_model=GraphResponse, tags=["analysis"])
def get_analysis_graph(analysis_id: str, service: AnalysisDependency) -> GraphResponse:
    try:
        return GraphResponse(graph=service.graph(analysis_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/api/v1/baselines/run",
    response_model=BaselineRunResponse,
    tags=["evaluation"],
)
def run_baseline(request: BaselineRunRequest) -> BaselineRunResponse:
    benchmark = load_frozen_benchmark()
    try:
        case = next(item for item in benchmark.cases if item.case_id == request.case_id)
    except StopIteration as error:
        raise HTTPException(status_code=404, detail="frozen benchmark case not found") from error
    runner = BaselineRunner()
    prediction, retrieval = runner.run(request.system, runner.case_input(case))
    return BaselineRunResponse(
        run_type="deterministic_fixture_validation",
        empirical_model_run=False,
        eligible_for_performance_claims=False,
        current_fda_operational_availability="not_operational",
        prediction=prediction,
        retrieval=retrieval,
    )


@router.post(
    "/api/v1/evaluations",
    response_model=EvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["evaluation"],
)
def create_evaluation(
    request: EvaluationCreateRequest, background_tasks: BackgroundTasks
) -> EvaluationResponse:
    try:
        run = _evaluation_manager.create(request.configuration_id)
    except EvaluationBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    background_tasks.add_task(_evaluation_manager.execute, run.id)
    return EvaluationResponse(evaluation=run)


@router.get(
    "/api/v1/evaluations/{evaluation_id}",
    response_model=EvaluationResponse,
    tags=["evaluation"],
)
def get_evaluation(evaluation_id: str) -> EvaluationResponse:
    try:
        return EvaluationResponse(evaluation=_evaluation_manager.get(evaluation_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/api/v1/presentation/m3",
    response_model=M4PresentationResponse,
    tags=["presentation"],
)
def get_m3_presentation() -> M4PresentationResponse:
    try:
        return M4PresentationResponse(snapshot=load_m4_snapshot())
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get(
    "/api/v1/presentation/m3/cases",
    response_model=M4PresentationCasesResponse,
    tags=["presentation"],
)
def get_m3_presentation_cases() -> M4PresentationCasesResponse:
    snapshot = load_m4_snapshot()
    return M4PresentationCasesResponse(
        snapshot_version=snapshot.snapshot_version,
        source_run_id=snapshot.source_run_id,
        cases=snapshot.cases,
    )


@router.get(
    "/api/v1/presentation/m3/cases/{case_id}",
    response_model=M4PresentationCasesResponse,
    tags=["presentation"],
)
def get_m3_presentation_case(case_id: str) -> M4PresentationCasesResponse:
    if "/" in case_id or "\\" in case_id or ".." in case_id:
        raise HTTPException(status_code=422, detail="case_id must be an opaque case identifier")
    snapshot = load_m4_snapshot()
    matching = tuple(case for case in snapshot.cases if case.case_id == case_id)
    if not matching:
        raise HTTPException(status_code=404, detail="presentation case not found")
    return M4PresentationCasesResponse(
        snapshot_version=snapshot.snapshot_version,
        source_run_id=snapshot.source_run_id,
        cases=matching,
    )


@router.get(
    "/api/v1/demo/presets",
    response_model=DemoPresetsResponse,
    tags=["presentation"],
)
def get_demo_presets() -> DemoPresetsResponse:
    return DemoPresetsResponse(presets=load_m4_snapshot().demo_presets)
