from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.analyzer.service import AnalysisPipelineError, AnalysisService
from app.config import Settings
from app.domain.models import AnalysisResult, TargetContext
from app.graph.models import GraphNeighborhood
from app.llm.responses import (
    LiveModelInvalidOutput,
    ResponsesStructuredModel,
    RetryableLiveModelError,
)
from app.parsers.profile322 import CAPABILITY_BOUNDARY
from app.parsers.public322 import PROFILE_ID as PUBLIC_PROFILE_ID
from app.product.models import (
    DossierAnalysisRequest,
    DossierAnalysisRun,
    DossierAnalysisSummary,
    DossierLeafFailure,
    DossierLeafResult,
    ModelExecutionRecord,
    ModelProfile,
)
from app.product.models_registry import ModelProfileRegistry
from app.product.repository import DossierRunRepository, InventoryRepository


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class CaptureRepository:
    """Transactional run-scoped persistence boundary used before product publication."""

    def __init__(self) -> None:
        self.result: AnalysisResult | None = None
        self.neighborhood: GraphNeighborhood | None = None

    def save(self, result: AnalysisResult, graph: GraphNeighborhood) -> None:
        validated_result = AnalysisResult.model_validate(result)
        validated_graph = GraphNeighborhood.model_validate(graph)
        self.result = validated_result
        self.neighborhood = validated_graph

    def get(self, analysis_id: str) -> AnalysisResult:
        if self.result is None or self.result.id != analysis_id:
            raise KeyError(analysis_id)
        return self.result

    def graph(self, analysis_id: str) -> GraphNeighborhood:
        if self.result is None or self.result.id != analysis_id or self.neighborhood is None:
            raise KeyError(analysis_id)
        return self.neighborhood


def execution_digest(
    profile: ModelProfile, target: TargetContext, leaf_ids: tuple[str, ...], kind: str
) -> str:
    return canonical_digest(
        {
            "pipeline": f"m4.2.2-{kind}-v1",
            "profile_configuration": profile.configuration_digest,
            "target": target.model_dump(mode="json"),
            "leaf_ids": sorted(leaf_ids),
        }
    )


def stable_run_id(prefix: str, package_sha256: str, configuration: str) -> str:
    return f"{prefix}-{hashlib.sha256(f'{package_sha256}|{configuration}'.encode()).hexdigest()}"


def _execution_record(
    profile: ModelProfile,
    result: AnalysisResult,
    model: object,
    retry_causes: tuple[str, ...] = (),
) -> ModelExecutionRecord:
    if result.model_run.mode != profile.execution_mode:
        raise ValueError("model result execution mode differs from the selected profile")
    attempt = None
    if isinstance(model, ResponsesStructuredModel) and model.last_attempts:
        attempt = model.last_attempts[-1]
    adapter: Literal["responses", "chat_completions", "fixture", "model-free"]
    if result.model_run.mode == "fixture":
        adapter = "fixture"
    else:
        adapter = profile.adapter_type
    return ModelExecutionRecord(
        model_profile_id=profile.model_id,
        requested_model_name=profile.configured_model_name,
        provider_reported_model_name=attempt.model_reported
        if attempt
        else result.model_run.model_name,
        adapter_type=adapter,
        execution_mode=cast(Literal["live", "fixture", "disabled"], result.model_run.mode),
        configuration_digest=profile.configuration_digest,
        prompt_version=result.model_run.prompt_template_version,
        request_digest=result.model_run.request_digest,
        input_tokens=result.model_run.input_tokens,
        output_tokens=result.model_run.output_tokens,
        reasoning_tokens=attempt.reasoning_tokens if attempt else None,
        latency_ms=result.model_run.latency_ms,
        attempt_count=1 + len(retry_causes),
        retry_causes=retry_causes,
        status=cast(
            Literal["completed", "abstained", "failed", "not_applicable"],
            result.model_run.status,
        ),
        reason_category=result.model_run.reason_category,
        status_detail=result.model_run.status_detail,
        failure=(
            result.model_run.validation_error if result.model_run.status == "failed" else None
        ),
    )


class DossierAnalysisManager:
    def __init__(
        self,
        *,
        inventories: InventoryRepository,
        runs: DossierRunRepository,
        registry: ModelProfileRegistry,
        settings: Settings,
    ) -> None:
        self.inventories = inventories
        self.runs = runs
        self.registry = registry
        self.settings = settings

    def create(self, request: DossierAnalysisRequest) -> DossierAnalysisRun:
        inventory = self.inventories.get(request.inventory_id)
        profile = self.registry.require(request.model_id)
        available = {leaf.id for leaf in inventory.leaves}
        leaf_ids = request.leaf_ids or tuple(leaf.id for leaf in inventory.leaves)
        if not leaf_ids or len(leaf_ids) != len(set(leaf_ids)) or set(leaf_ids) - available:
            raise ValueError("leaf selection must contain unique supported leaf IDs")
        config = execution_digest(profile, request.target_context, leaf_ids, "dossier")
        run_id = stable_run_id("dossier", inventory.package_sha256, config)
        now = datetime.now(UTC)
        run = DossierAnalysisRun(
            run_id=run_id,
            state="queued",
            inventory_id=inventory.id,
            input_profile_id=inventory.input_profile_id,
            selected_model=profile,
            target_context=request.target_context,
            execution_configuration_digest=config,
            requested_leaf_ids=leaf_ids,
            created_at=now,
            updated_at=now,
            capability_boundary=(
                "RegBridge accepts and validates the bounded FDA/CDER eCTD v3.2.2 public-"
                "standards input profile against pinned local ICH/FDA DTDs. This is not full "
                "FDA validation or submission-readiness assessment."
                if inventory.input_profile_id == PUBLIC_PROFILE_ID
                else CAPABILITY_BOUNDARY
            ),
        )
        self.runs.put(run_id, run)
        return run

    async def execute(self, run_id: str) -> None:
        run = self.runs.get(run_id)
        inventory = self.inventories.get(run.inventory_id)
        run = run.model_copy(update={"state": "running", "updated_at": datetime.now(UTC)})
        self.runs.put(run_id, run)
        results: list[DossierLeafResult] = []
        failures: list[DossierLeafFailure] = []
        for leaf_id in run.requested_leaf_ids:
            retry_causes: list[str] = []
            for attempt_index in range(3):
                model = self.registry.create(run.selected_model.model_id)
                capture = CaptureRepository()
                service = AnalysisService(
                    model=model, repository=cast(Any, capture), settings=self.settings
                )
                try:
                    result = await service.analyze_async(inventory, leaf_id, run.target_context)
                    if result.model_run.status == "failed":
                        raise AnalysisPipelineError(
                            "semantic_processing",
                            RuntimeError("analysis returned a failed model execution"),
                        )
                    if capture.neighborhood is None:
                        raise AnalysisPipelineError(
                            "persistence", RuntimeError("graph was not committed")
                        )
                    results.append(
                        DossierLeafResult(
                            leaf_id=leaf_id,
                            analysis_ref=f"{run_id}-{leaf_id}",
                            analysis=result,
                            graph=capture.neighborhood,
                            model=_execution_record(
                                run.selected_model, result, model, tuple(retry_causes)
                            ),
                        )
                    )
                    break
                except RetryableLiveModelError as error:
                    cause = str(error).strip() or type(error).__name__
                    retry_causes.append(cause)
                    if attempt_index < 2:
                        continue
                    failures.append(
                        DossierLeafFailure(
                            leaf_id=leaf_id,
                            stage="transport",
                            cause=f"RetryableLiveModelError:{cause}",
                            failure_category="transport_or_provider_failure",
                            retryable=False,
                        )
                    )
                    break
                except (
                    LiveModelInvalidOutput,
                    AnalysisPipelineError,
                    ValueError,
                    KeyError,
                ) as error:
                    stage = error.stage if isinstance(error, AnalysisPipelineError) else "analysis"
                    failures.append(
                        DossierLeafFailure(
                            leaf_id=leaf_id,
                            stage=stage,
                            cause=type(error).__name__,
                            failure_category=(
                                "invalid_structured_output"
                                if isinstance(error, LiveModelInvalidOutput)
                                or stage in {"semantic_processing", "semantic_validation"}
                                else (
                                    "graph_failure"
                                    if stage == "graph"
                                    else (
                                        "persistence_failure"
                                        if stage == "persistence"
                                        else "analysis_failure"
                                    )
                                )
                            ),
                            retryable=False,
                        )
                    )
                    break
        decisions: dict[str, int] = {}
        severities: dict[str, int] = {}
        for item in results:
            decisions[item.analysis.decision.value] = (
                decisions.get(item.analysis.decision.value, 0) + 1
            )
            severities[item.analysis.severity.value] = (
                severities.get(item.analysis.severity.value, 0) + 1
            )
        summary = DossierAnalysisSummary(
            package_sha256=inventory.package_sha256,
            application_number=inventory.application_number,
            submission_type=inventory.submission_type,
            applicant_name=inventory.applicant_name,
            total_supported_leaves=len(inventory.leaves),
            analyzed_count=len(results),
            failed_count=len(failures),
            pipeline_failure_count=len(failures),
            model_abstention_count=sum(item.model.status == "abstained" for item in results),
            skipped_count=len(inventory.leaves) - len(run.requested_leaf_ids),
            decision_counts=decisions,
            severity_counts=severities,
            human_approval_count=sum(item.analysis.human_approval_required for item in results),
            parser_warning_count=len(inventory.warnings),
            policy_coverage_counts={
                str(key): value for key, value in inventory.policy_coverage_counts.items()
            },
            model_profile_id=run.selected_model.model_id,
            model_configuration_digest=run.selected_model.configuration_digest,
        )
        state = "completed" if not failures else ("partial_failed" if results else "failed")
        self.runs.put(
            run_id,
            run.model_copy(
                update={
                    "state": state,
                    "updated_at": datetime.now(UTC),
                    "summary": summary,
                    "results": tuple(results),
                    "failures": tuple(failures),
                }
            ),
        )
