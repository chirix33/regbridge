from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.analyzer.service import AnalysisPipelineError, AnalysisService
from app.baselines.direct import (
    DIRECT_INPUT_CHARACTER_LIMIT,
    PreparedCase,
    serialize_direct_request,
)
from app.baselines.retrieval import BM25Retriever
from app.baselines.runner import OmittedSemanticModel
from app.config import Settings
from app.domain.enums import Decision, Severity
from app.domain.models import DossierEvidence
from app.evaluation.models import DirectDecisionOutput
from app.llm.protocol import StructuredModel
from app.llm.responses import (
    LiveModelInvalidOutput,
    ResponsesStructuredModel,
    RetryableLiveModelError,
)
from app.llm.serialization import RequestAliases
from app.product.models import (
    ComparisonCell,
    ComparisonRequest,
    ComparisonRun,
    DossierLeafFailure,
    ModelExecutionRecord,
    RetrievalItem,
)
from app.product.models_registry import ModelProfileRegistry, ProductFixtureModel
from app.product.repository import ComparisonRunRepository, InventoryRepository
from app.product.services import (
    CaptureRepository,
    canonical_digest,
    execution_digest,
    stable_run_id,
)
from app.standards.evidence import EvidenceRegistry


def package_material(
    inventory: Any, leaf: Any, target: Any
) -> tuple[dict[str, Any], dict[str, str]]:
    dossier: tuple[DossierEvidence, ...] = AnalysisService._dossier_evidence(
        f"artifact-{leaf.id}", leaf
    )
    forbidden = (
        leaf.id,
        inventory.id,
        *(value for item in dossier for value in (item.id, item.artifact_id, item.locator)),
    )
    aliases = RequestAliases(forbidden=forbidden)
    alias_map: dict[str, str] = {}
    evidence: list[dict[str, str]] = []
    for index, item in enumerate(dossier, start=1):
        alias = f"dossier-evidence-{index:03d}"
        alias_map[alias] = item.id
        evidence.append({"id": alias, "kind": item.kind, "text": aliases.text(item.text)})
    material = aliases.clean(
        {
            "source_standard": inventory.source_standard.value,
            "application": {
                "application_type": inventory.submission_type,
                "applicant_name": inventory.applicant_name,
                "input_profile_id": inventory.input_profile_id,
                "package_profile_status": inventory.package_profile_status,
            },
            "selected_leaf": {
                "title": leaf.title,
                "heading": leaf.heading,
                "raw_heading": leaf.raw_heading,
                "heading_status": leaf.heading_status,
                "operation": leaf.operation.value,
                "has_modified_file": leaf.modified_leaf_id is not None,
                "keywords": [
                    {"name": item.name, "value": item.normalized_value} for item in leaf.keywords
                ],
                "dossier_evidence": evidence,
                "extraction_status": leaf.extraction_status,
                "policy_coverage_status": leaf.policy_coverage_status,
                "policy_coverage_basis": leaf.policy_coverage_basis,
                "covered_policy_ids": list(leaf.covered_policy_ids),
            },
            "target_context": target.model_dump(mode="json"),
            "operational_availability": "not_operational",
        }
    )
    serialized = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if any(item in serialized for item in forbidden):
        raise ValueError("internal package or evidence identity leaked into direct input")
    return material, alias_map


def _fixture_direct(material: dict[str, Any], standards_ids: set[str]) -> DirectDecisionOutput:
    selected = material["selected_leaf"]
    target = material["target_context"]
    evidence = selected["dossier_evidence"]
    text = " ".join(item["text"] for item in evidence if item["kind"] == "text").casefold()
    keywords = {item["name"]: item["value"] for item in selected["keywords"]}
    if target["scenario_mode"] == "current_operational":
        return DirectDecisionOutput(
            decision=Decision.HUMAN_REGULATORY_REVIEW,
            severity=Severity.UNRESOLVED,
            action="WAIT_FOR_OPERATIONAL_AVAILABILITY",
            human_review_required=True,
            rationale="Forward compatibility is not operational.",
            confidence=1,
        )
    if selected["policy_coverage_status"] in {
        "OUTSIDE_ENCODED_POLICY_COVERAGE",
        "INSUFFICIENT_APPLICATION_HISTORY",
        "DOCUMENT_INSPECTION_INCOMPLETE",
    }:
        return DirectDecisionOutput(
            decision=Decision.HUMAN_REGULATORY_REVIEW,
            severity=Severity.UNRESOLVED,
            action="AUTHOR_REVIEW_HEADING_MAPPING"
            if selected["policy_coverage_status"] == "OUTSIDE_ENCODED_POLICY_COVERAGE"
            else "HUMAN_VERIFY_STALE_CONTENT",
            human_review_required=True,
            rationale=str(selected["policy_coverage_basis"]),
            confidence=0,
        )
    if selected["heading"] in {"3.2.S.1.1", "3.2.S.1.2", "3.2.S.1.3"}:
        enough = {"ev-ctoc-3211-3213-removed", "ev-tcg-new-context-and-reuse"} <= standards_ids
        return DirectDecisionOutput(
            decision=Decision.REUSE_WITH_NEW_CONTEXT
            if enough
            else Decision.HUMAN_REGULATORY_REVIEW,
            severity=Severity.BLOCKING if enough else Severity.UNRESOLVED,
            action="CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT"
            if enough
            else "AUTHOR_REVIEW_HEADING_MAPPING",
            human_review_required=True,
            rationale="The supplied heading and standards evidence require a placement decision.",
            evidence_ids=tuple(sorted(standards_ids)),
            confidence=0.9,
        )
    applicant = str(material["application"].get("applicant_name") or "").casefold()
    if "responsible applicant" in text and applicant and applicant not in text:
        cited = tuple(item["id"] for item in evidence if item["kind"] == "text")
        return DirectDecisionOutput(
            decision=Decision.HUMAN_REGULATORY_REVIEW,
            severity=Severity.UNRESOLVED,
            action="HUMAN_VERIFY_STALE_CONTENT",
            human_review_required=True,
            rationale="Document wording differs from supplied regional applicant metadata.",
            evidence_ids=cited,
            confidence=0.95,
        )
    if (
        keywords.get("manufacturer") == "all"
        and target.get("metadata_plan", {}).get("intent") == "preserve-existing-lifecycle"
    ):
        cited = tuple(item["id"] for item in evidence if item["kind"] == "metadata")
        return DirectDecisionOutput(
            decision=Decision.REUSE_AS_LEGACY_REFERENCE,
            severity=Severity.MEDIUM,
            action="PRESERVE_EXACT_CONTEXT_GROUP_KEYWORDS",
            human_review_required=True,
            rationale=(
                "The supplied preservation intent retains the existing context metadata with "
                "human approval."
            ),
            evidence_ids=cited,
            confidence=0.85,
        )
    return DirectDecisionOutput(
        decision=Decision.REUSE_AS_LEGACY_REFERENCE,
        severity=Severity.INFORMATIONAL,
        action="NO_MATERIAL_REPAIR",
        human_review_required=False,
        rationale="No material issue was identified in the supplied bounded packet.",
        confidence=0.8,
    )


async def _direct_output(
    model: object, serialized: str, material: dict[str, Any], standards_ids: set[str]
) -> tuple[DirectDecisionOutput, ModelExecutionRecord]:
    started = time.perf_counter()
    if isinstance(model, ProductFixtureModel):
        output = _fixture_direct(material, standards_ids)
        return output, ModelExecutionRecord(
            model_profile_id="gpt-5.5",
            requested_model_name="internal-package-derived-fixture",
            provider_reported_model_name="internal-package-derived-fixture",
            adapter_type="fixture",
            execution_mode="fixture",
            configuration_digest=hashlib.sha256(b"m4.1-internal-direct-fixture-v1").hexdigest(),
            prompt_version="1.0.0",
            request_digest=hashlib.sha256(serialized.encode()).hexdigest(),
            input_tokens=(len(serialized) + 3) // 4,
            output_tokens=(len(output.model_dump_json()) + 3) // 4,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="completed",
        )
    if not isinstance(model, ResponsesStructuredModel):
        raise TypeError("direct product execution requires ResponsesStructuredModel")
    completion = await model.complete_text(
        input_text=serialized, output_type=DirectDecisionOutput, prompt_template_version="1.0.0"
    )
    attempt = model.last_attempts[-1]
    return completion.output, ModelExecutionRecord(
        model_profile_id="gpt-5.5",
        requested_model_name=attempt.model_requested,
        provider_reported_model_name=attempt.model_reported,
        adapter_type="responses",
        execution_mode="live",
        configuration_digest=hashlib.sha256(
            json.dumps(
                {
                    "model": attempt.model_requested,
                    "reasoning": attempt.reasoning_effort,
                    "max_output_tokens": attempt.max_output_tokens,
                    "temperature_handling": attempt.temperature_handling,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        prompt_version="1.0.0",
        request_digest=attempt.request_digest,
        input_tokens=attempt.input_tokens,
        output_tokens=attempt.total_output_tokens,
        reasoning_tokens=attempt.reasoning_tokens,
        latency_ms=attempt.latency_ms,
        status="completed",
    )


async def _pipeline_output(
    *,
    inventory: Any,
    leaf_id: str,
    target: Any,
    semantic_model: object,
    settings: Settings,
) -> tuple[Any, CaptureRepository]:
    capture = CaptureRepository()
    service = AnalysisService(
        model=cast(StructuredModel, semantic_model),
        repository=cast(Any, capture),
        settings=settings,
    )
    result = await service.analyze_async(inventory, leaf_id, target)
    if capture.neighborhood is None:
        raise AnalysisPipelineError("persistence", RuntimeError("graph missing"))
    return result, capture


class ComparisonManager:
    def __init__(
        self,
        *,
        inventories: InventoryRepository,
        runs: ComparisonRunRepository,
        registry: ModelProfileRegistry,
        settings: Settings,
    ) -> None:
        self.inventories = inventories
        self.runs = runs
        self.registry = registry
        self.settings = settings
        self.evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
        self.evidence_by_id = {item.id: item for item in self.evidence}
        self.retriever = BM25Retriever(self.evidence)

    def create(self, request: ComparisonRequest) -> ComparisonRun:
        inventory = self.inventories.get(request.inventory_id)
        profile = self.registry.require(request.model_id)
        available = {leaf.id for leaf in inventory.leaves}
        leaf_ids = request.leaf_ids or tuple(leaf.id for leaf in inventory.leaves)
        if not leaf_ids or len(leaf_ids) != len(set(leaf_ids)) or set(leaf_ids) - available:
            raise ValueError("leaf selection must contain unique supported leaf IDs")
        config = execution_digest(profile, request.target_context, leaf_ids, "comparison")
        run_id = stable_run_id("comparison", inventory.package_sha256, config)
        now = datetime.now(UTC)
        run = ComparisonRun(
            comparison_id=run_id,
            state="queued",
            inventory_id=inventory.id,
            input_profile_id=inventory.input_profile_id,
            selected_model=profile,
            target_context=request.target_context,
            execution_configuration_digest=config,
            requested_leaf_ids=leaf_ids,
            created_at=now,
            updated_at=now,
        )
        self.runs.put(run_id, run)
        return run

    async def execute(self, comparison_id: str) -> None:
        run = self.runs.get(comparison_id)
        inventory = self.inventories.get(run.inventory_id)
        run = run.model_copy(update={"state": "running", "updated_at": datetime.now(UTC)})
        self.runs.put(comparison_id, run)
        cells: list[ComparisonCell] = []
        failures: list[DossierLeafFailure] = []
        for leaf_id in run.requested_leaf_ids:
            leaf = next(item for item in inventory.leaves if item.id == leaf_id)
            material, alias_map = package_material(inventory, leaf, run.target_context)
            prepared = PreparedCase(
                material=material,
                serialized=json.dumps(material, sort_keys=True, separators=(",", ":")),
                alias_to_evidence_id=alias_map,
            )
            input_digest = canonical_digest(material)
            for system in ("B0", "B1"):
                selected = self.evidence
                retrieval: tuple[RetrievalItem, ...] = ()
                if system == "B1":
                    trace = self.retriever.retrieve(
                        case_id="package-input", query=prepared.serialized
                    )
                    selected = tuple(self.evidence_by_id[item.evidence_id] for item in trace.hits)
                    retrieval = tuple(
                        RetrievalItem(
                            alias=f"standards-evidence-{item.rank:03d}",
                            evidence_id=item.evidence_id,
                            score=item.score,
                            rank=item.rank,
                        )
                        for item in trace.hits
                    )
                serialized = serialize_direct_request(prepared, selected)
                if len(serialized) > DIRECT_INPUT_CHARACTER_LIMIT:
                    raise ValueError("direct product input exceeds fixed character limit")
                retry_causes: list[str] = []
                output: DirectDecisionOutput | None = None
                record: ModelExecutionRecord | None = None
                terminal_error: Exception | None = None
                try:
                    for attempt_index in range(3):
                        model = self.registry.create(run.selected_model.model_id)
                        try:
                            output, record = await _direct_output(
                                model, serialized, material, {item.id for item in selected}
                            )
                            break
                        except RetryableLiveModelError as error:
                            cause = str(error).strip() or type(error).__name__
                            retry_causes.append(cause)
                            if attempt_index == 2:
                                terminal_error = error
                    if terminal_error is not None or output is None or record is None:
                        raise terminal_error or RuntimeError("direct model produced no result")
                    record = record.model_copy(
                        update={
                            "attempt_count": 1 + len(retry_causes),
                            "retry_causes": tuple(retry_causes),
                        }
                    )
                    supplied = set(alias_map) | {item.id for item in selected}
                    if set(output.evidence_ids) - supplied:
                        raise LiveModelInvalidOutput("unsupported_citation")
                    translated = tuple(alias_map.get(item, item) for item in output.evidence_ids)
                    cells.append(
                        ComparisonCell(
                            leaf_id=leaf_id,
                            system=system,
                            package_sha256=inventory.package_sha256,
                            selected_file_sha256=leaf.file_sha256,
                            package_input_digest=input_digest,
                            model=record.model_copy(
                                update={
                                    "configuration_digest": run.selected_model.configuration_digest
                                }
                            ),
                            decision=output.decision,
                            severity=output.severity,
                            action=output.action,
                            human_review_required=output.human_review_required,
                            rationale=output.rationale,
                            evidence_ids=translated,
                            retrieval=retrieval,
                            status="completed",
                        )
                    )
                except (LiveModelInvalidOutput, RetryableLiveModelError, RuntimeError) as error:
                    failures.append(
                        DossierLeafFailure(
                            leaf_id=leaf_id,
                            stage=f"{system}-model",
                            cause=type(error).__name__,
                            retryable=isinstance(error, RetryableLiveModelError),
                        )
                    )
                    cells.append(
                        ComparisonCell(
                            leaf_id=leaf_id,
                            system=system,
                            package_sha256=inventory.package_sha256,
                            selected_file_sha256=leaf.file_sha256,
                            package_input_digest=input_digest,
                            model=ModelExecutionRecord(
                                model_profile_id=run.selected_model.model_id,
                                requested_model_name=run.selected_model.configured_model_name,
                                adapter_type=(
                                    run.selected_model.actual_adapter_type
                                    or run.selected_model.adapter_type
                                ),
                                execution_mode=run.selected_model.execution_mode,
                                configuration_digest=run.selected_model.configuration_digest,
                                prompt_version="1.0.0",
                                latency_ms=0,
                                attempt_count=max(1, len(retry_causes)),
                                retry_causes=tuple(retry_causes),
                                status="failed",
                                failure=type(error).__name__,
                            ),
                            retrieval=retrieval,
                            status="invalid_output",
                            failure=type(error).__name__,
                        )
                    )
            for system in cast(tuple[Literal["B2", "RegBridge"], ...], ("B2", "RegBridge")):
                retry_causes = []
                semantic_model: object = OmittedSemanticModel()
                try:
                    if system == "B2":
                        result, capture = await _pipeline_output(
                            inventory=inventory,
                            leaf_id=leaf_id,
                            target=run.target_context,
                            semantic_model=semantic_model,
                            settings=self.settings,
                        )
                    else:
                        pipeline_terminal_error: Exception | None = None
                        result = None
                        capture = CaptureRepository()
                        for attempt_index in range(3):
                            semantic_model = self.registry.create(run.selected_model.model_id)
                            try:
                                result, capture = await _pipeline_output(
                                    inventory=inventory,
                                    leaf_id=leaf_id,
                                    target=run.target_context,
                                    semantic_model=semantic_model,
                                    settings=self.settings,
                                )
                                break
                            except RetryableLiveModelError as error:
                                cause = str(error).strip() or type(error).__name__
                                retry_causes.append(cause)
                                if attempt_index == 2:
                                    pipeline_terminal_error = error
                        if pipeline_terminal_error is not None or result is None:
                            raise pipeline_terminal_error or RuntimeError(
                                "RegBridge model produced no result"
                            )
                    if system == "B2":
                        record = ModelExecutionRecord(
                            model_profile_id="model-free",
                            adapter_type="model-free",
                            execution_mode="disabled",
                            configuration_digest=canonical_digest(
                                {"system": "B2", "rules": "production", "semantic": "omitted"}
                            ),
                            prompt_version="not-applicable",
                            latency_ms=0,
                            attempt_count=0,
                            status="not_applicable",
                        )
                    else:
                        from app.product.services import _execution_record

                        record = _execution_record(
                            run.selected_model, result, semantic_model, tuple(retry_causes)
                        )
                    cells.append(
                        ComparisonCell(
                            leaf_id=leaf_id,
                            system=system,
                            package_sha256=inventory.package_sha256,
                            selected_file_sha256=leaf.file_sha256,
                            package_input_digest=input_digest,
                            model=record,
                            decision=result.decision,
                            severity=result.severity,
                            action=result.repair.type,
                            human_review_required=result.human_approval_required,
                            rationale=result.rationale,
                            evidence_ids=tuple(item.id for item in result.evidence),
                            rule_ids=result.triggered_rule_ids,
                            graph=capture.neighborhood,
                            trace=tuple(step.model_dump(mode="json") for step in result.trace),
                            status="completed",
                        )
                    )
                except (
                    LiveModelInvalidOutput,
                    RetryableLiveModelError,
                    AnalysisPipelineError,
                    ValueError,
                    RuntimeError,
                ) as error:
                    failures.append(
                        DossierLeafFailure(
                            leaf_id=leaf_id,
                            stage=f"{system}-analysis",
                            cause=type(error).__name__,
                            retryable=isinstance(error, RetryableLiveModelError),
                        )
                    )
        state = "completed" if not failures else ("partial_failed" if cells else "failed")
        self.runs.put(
            comparison_id,
            run.model_copy(
                update={
                    "state": state,
                    "updated_at": datetime.now(UTC),
                    "results": tuple(cells),
                    "failures": tuple(failures),
                }
            ),
        )
