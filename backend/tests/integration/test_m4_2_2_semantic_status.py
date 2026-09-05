from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

import pytest
from app.analyzer.service import AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import (
    ApplicationType,
    Authority,
    Center,
    LlmMode,
    ManufacturerPartitioning,
    MetadataMigrationIntent,
    ReuseOperation,
    ScenarioMode,
    StandardVersion,
)
from app.domain.models import MetadataPlan, ModelRunRecord, TargetContext
from app.llm.models import ModelCompletion, ModelRequest, SemanticFinding, SemanticRiskOutput
from app.llm.responses import (
    LiveModelInvalidOutput,
    ResponsesStructuredModel,
    RetryableLiveModelError,
)
from app.parsers.public322 import parse_public_profile_zip
from app.product.models import DossierAnalysisRequest
from app.product.models_registry import ModelProfileRegistry, ProductFixtureModel
from app.product.repository import DossierRunRepository, InventoryRepository
from app.product.services import (
    CaptureRepository,
    DossierAnalysisManager,
    _execution_record,
)
from pydantic import BaseModel, SecretStr

OutputT = TypeVar("OutputT", bound=BaseModel)
PACKAGE = (
    REPOSITORY_ROOT / "data" / "demo-dossiers" / "m4-2" / "regbridge-m4-2-public-standards.zip"
)


def _target(
    scenario: ScenarioMode = ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
) -> TargetContext:
    return TargetContext(
        authority=Authority.FDA,
        center=Center.CDER,
        application_type=ApplicationType.NDA,
        source_standard=StandardVersion.ECTD_3_2_2,
        target_standard=StandardVersion.ECTD_4_0,
        analysis_date=date(2026, 9, 4),
        reuse_operation=ReuseOperation.REFERENCE_EXISTING_CONTENT,
        standards_snapshot_id="fda-cder-demo-v1",
        scenario_mode=scenario,
        metadata_plan=MetadataPlan(
            intent=MetadataMigrationIntent.PRESERVE_EXISTING_LIFECYCLE,
            manufacturer_partitioning=ManufacturerPartitioning.UNKNOWN,
        ),
    )


def _inventory() -> Any:
    return parse_public_profile_zip(PACKAGE.read_bytes())


class StaticSemanticModel:
    last_attempts: tuple[object, ...] = ()

    def __init__(
        self,
        *,
        abstained: bool = False,
        findings: tuple[SemanticFinding, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self.abstained = abstained
        self.findings = findings
        self.error = error

    async def complete(
        self, request: ModelRequest, output_type: type[OutputT]
    ) -> ModelCompletion[OutputT]:
        if self.error is not None:
            raise self.error
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=self.abstained,
            abstain_reason="insufficient bounded evidence" if self.abstained else None,
            findings=self.findings,
            confidence=0 if self.abstained else 0.9,
        )
        return ModelCompletion(
            output=output_type.model_validate(output.model_dump()),
            run=ModelRunRecord(
                mode="fixture",
                status="abstained" if self.abstained else "completed",
                prompt_template_version=request.prompt_template_version,
                model_name="m4.2.2-scripted-fixture",
                request_digest="1" * 64,
                latency_ms=0,
            ),
        )


async def _analyze(title: str, model: object) -> tuple[Any, Any]:
    inventory = _inventory()
    leaf = next(item for item in inventory.leaves if item.title == title)
    capture = CaptureRepository()
    result = await AnalysisService(
        model=model,  # type: ignore[arg-type]
        repository=capture,  # type: ignore[arg-type]
        settings=Settings(llm_mode=LlmMode.FIXTURE),
    ).analyze_async(inventory, leaf.id, _target())
    assert capture.neighborhood is not None
    return result, capture.neighborhood


def test_completed_abstained_and_not_applicable_statuses_remain_distinct() -> None:
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    profile = ModelProfileRegistry(settings).require("gpt-5.5")
    clean_model = StaticSemanticModel()
    clean, _ = asyncio.run(_analyze("Synthetic lifecycle metadata context", clean_model))
    assert clean.model_run.status == "completed"
    assert _execution_record(profile, clean, clean_model).status == "completed"

    abstaining_model = StaticSemanticModel(abstained=True)
    abstained, _ = asyncio.run(_analyze("Synthetic lifecycle metadata context", abstaining_model))
    record = _execution_record(profile, abstained, abstaining_model)
    assert abstained.model_run.validation_error is None
    assert record.status == "abstained"
    assert record.failure is None
    assert record.reason_category == "insufficient_bounded_evidence"

    inventory = _inventory()
    leaf = inventory.leaves[0]
    capture = CaptureRepository()
    not_applicable = asyncio.run(
        AnalysisService(
            model=ProductFixtureModel(),
            repository=capture,  # type: ignore[arg-type]
            settings=settings,
        ).analyze_async(inventory, leaf.id, _target(ScenarioMode.CURRENT_OPERATIONAL))
    )
    assert _execution_record(profile, not_applicable, ProductFixtureModel()).status == (
        "not_applicable"
    )


def test_case_a_abstention_qualifies_but_does_not_erase_hard_decision() -> None:
    result, graph = asyncio.run(
        _analyze("Synthetic molecular structure", StaticSemanticModel(abstained=True))
    )
    assert result.decision.value == "REUSE_WITH_NEW_CONTEXT"
    assert result.repair.type == "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT"
    assert result.human_approval_required is True
    assert result.decision_basis == "deterministic_hard_rule"
    assert result.model_run.status == "abstained"
    assert result.unresolved_uncertainty
    assert "not semantically cleared" in result.rationale
    assert {node.label for node in graph.nodes if node.type.value == "heading"} == {
        "3.2.S.1.2",
        "3.2.S.1 General information",
    }
    limitation = next(node for node in graph.nodes if node.type.value == "analysis_limitation")
    assert limitation.review_status is None
    assert not any(node.type.value == "model_finding" for node in graph.nodes)
    edge = next(item for item in graph.edges if item.source == limitation.id)
    assert edge.type.value == "QUALIFIES_DECISION"


def test_case_a_completed_clean_inspection_keeps_active_mapping() -> None:
    result, graph = asyncio.run(_analyze("Synthetic molecular structure", StaticSemanticModel()))
    assert result.decision.value == "REUSE_WITH_NEW_CONTEXT"
    assert result.model_run.status == "completed"
    assert result.repair.type == "CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT"
    assert len([edge for edge in graph.edges if edge.type.value == "MAPS_TO"]) == 1
    assert not any("3.2.S.1.1" in node.label for node in graph.nodes)
    assert not any("3.2.S.1.3" in node.label for node in graph.nodes)


def test_case_b_clean_and_abstention_paths_are_semantically_distinct() -> None:
    clean, _ = asyncio.run(_analyze("Synthetic lifecycle metadata context", StaticSemanticModel()))
    assert clean.decision.value == "REUSE_AS_LEGACY_REFERENCE"
    assert clean.model_run.status == "completed"
    assert any(
        'manufacturer value normalizes to "all"' in item.rationale for item in clean.findings
    )

    abstained, graph = asyncio.run(
        _analyze("Synthetic lifecycle metadata context", StaticSemanticModel(abstained=True))
    )
    assert abstained.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert abstained.repair.type == "COMPLETE_DOCUMENT_INSPECTION"
    assert abstained.decision_basis == "abstention_gate"
    assert "stale" not in abstained.rationale.casefold()
    assert not any(item.source.value == "model_assisted" for item in abstained.findings)
    assert {"dossier_evidence", "keyword", "rule", "analysis_limitation", "decision"} <= {
        node.type.value for node in graph.nodes
    }
    limitation = next(node for node in graph.nodes if node.type.value == "analysis_limitation")
    assert any(
        edge.source == limitation.id and edge.type.value == "LEAVES_UNRESOLVED"
        for edge in graph.edges
    )


def test_case_c_supported_mismatch_abstention_and_clean_paths() -> None:
    mismatch, mismatch_graph = asyncio.run(
        _analyze("Synthetic applicant responsibility statement", ProductFixtureModel())
    )
    assert mismatch.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert mismatch.repair.type == "HUMAN_VERIFY_STALE_CONTENT"
    assert mismatch.decision_basis == "semantic_finding"
    model_node = next(node for node in mismatch_graph.nodes if node.type.value == "model_finding")
    assert any(
        edge.source == model_node.id and edge.type.value == "CITES" for edge in mismatch_graph.edges
    )

    abstained, abstained_graph = asyncio.run(
        _analyze(
            "Synthetic applicant responsibility statement",
            StaticSemanticModel(abstained=True),
        )
    )
    assert abstained.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert abstained.repair.type == "COMPLETE_DOCUMENT_INSPECTION"
    assert "stale" not in abstained.rationale.casefold()
    assert not any(node.type.value == "model_finding" for node in abstained_graph.nodes)

    clean, _ = asyncio.run(
        _analyze("Synthetic applicant responsibility statement", StaticSemanticModel())
    )
    assert clean.decision.value == "REUSE_AS_LEGACY_REFERENCE"
    assert clean.repair.type == "NO_MATERIAL_REPAIR"


class RegistryDouble:
    def __init__(self, settings: Settings, factory: Any) -> None:
        self.base = ModelProfileRegistry(settings)
        self.factory = factory

    def require(self, model_id: str) -> Any:
        return self.base.require(model_id)

    def create(self, model_id: str) -> Any:
        self.require(model_id)
        return self.factory()


def _manager(
    registry: Any,
    settings: Settings,
    leaf_ids: tuple[str, ...] | None = None,
) -> tuple[Any, str]:
    inventory = _inventory()
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(inventory)
    runs = DossierRunRepository(capacity=2, ttl_seconds=60, prefix="dossier")
    manager = DossierAnalysisManager(
        inventories=inventories,
        runs=runs,
        registry=registry,
        settings=settings,
    )
    run = manager.create(
        DossierAnalysisRequest(
            inventory_id=envelope.inventory_id,
            model_id="gpt-5.5",
            target_context=_target(),
            leaf_ids=leaf_ids,
        )
    )
    asyncio.run(manager.execute(run.run_id))
    return runs.get(run.run_id), run.run_id


def test_invalid_output_is_terminal_and_never_becomes_human_review() -> None:
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    leaf_id = _inventory().leaves[0].id
    run, _ = _manager(
        RegistryDouble(
            settings,
            lambda: StaticSemanticModel(error=LiveModelInvalidOutput("schema_validation")),
        ),
        settings,
        (leaf_id,),
    )
    assert run.results == ()
    assert len(run.failures) == 1
    assert run.failures[0].failure_category == "invalid_structured_output"
    assert run.summary.analyzed_count == 0
    assert run.summary.human_approval_count == 0
    assert run.summary.pipeline_failure_count == 1


def test_retryable_failure_uses_exact_attempt_limit_then_fails_leaf() -> None:
    settings = Settings(llm_mode=LlmMode.FIXTURE)
    calls = 0

    class RetryModel(StaticSemanticModel):
        async def complete(self, request: ModelRequest, output_type: type[OutputT]) -> Any:
            nonlocal calls
            calls += 1
            raise RetryableLiveModelError("redacted provider failure")

    leaf_id = _inventory().leaves[0].id
    run, _ = _manager(RegistryDouble(settings, RetryModel), settings, (leaf_id,))
    assert calls == 3
    assert run.results == ()
    assert run.failures[0].failure_category == "transport_or_provider_failure"
    assert run.summary.pipeline_failure_count == 1


def test_summary_separates_completed_abstained_and_terminal_failure() -> None:
    settings = Settings(llm_mode=LlmMode.FIXTURE)

    class RoutingModel(StaticSemanticModel):
        async def complete(
            self, request: ModelRequest, output_type: type[OutputT]
        ) -> ModelCompletion[OutputT]:
            artifact = next(
                item.artifact_id for item in request.evidence if hasattr(item, "artifact_id")
            )
            if artifact.endswith("leaf-a"):
                return await StaticSemanticModel().complete(request, output_type)
            if artifact.endswith("leaf-b"):
                return await StaticSemanticModel(abstained=True).complete(request, output_type)
            raise ValueError("invalid scripted structured output")

    run, _ = _manager(RegistryDouble(settings, RoutingModel), settings)
    assert run.summary.analyzed_count == 2
    assert run.summary.human_approval_count == 2
    assert run.summary.model_abstention_count == 1
    assert run.summary.pipeline_failure_count == 1
    assert run.summary.failed_count == 1
    assert len(run.failures) == 1
    assert all(item.model.status != "failed" for item in run.results)


def test_execution_mode_controls_profile_availability_and_adapter_construction() -> None:
    fixture = ModelProfileRegistry(Settings(llm_mode=LlmMode.FIXTURE))
    fixture_profile = fixture.require("gpt-5.5")
    assert fixture_profile.execution_mode == "fixture"
    assert fixture_profile.actual_adapter_type == "fixture"
    assert isinstance(fixture.create("gpt-5.5"), ProductFixtureModel)

    live = ModelProfileRegistry(
        Settings(
            llm_mode=LlmMode.LIVE,
            llm_base_url="https://example.invalid/v1",
            llm_api_key=SecretStr("redacted-test-key"),
            llm_model="gpt-5.5",
        )
    )
    live_profile = live.require("gpt-5.5")
    assert live_profile.execution_mode == "live"
    assert live_profile.actual_adapter_type == "responses"
    assert isinstance(live.create("gpt-5.5"), ResponsesStructuredModel)

    disabled = ModelProfileRegistry(
        Settings(
            llm_mode=LlmMode.DISABLED,
            llm_base_url="https://example.invalid/v1",
            llm_api_key=SecretStr("present-but-disabled"),
            llm_model="gpt-5.5",
        )
    )
    disabled_profile = disabled.catalog().models[0]
    assert disabled_profile.availability == "disabled"
    assert disabled_profile.actual_adapter_type is None
    with pytest.raises(ValueError, match="disabled"):
        disabled.create("gpt-5.5")


def test_protected_package_bytes_are_unchanged() -> None:
    expected = "4d236d51694b1c15d37ad92b9d0074b97a15075cde86cb96c393b9f87ce3e6e4"
    import hashlib

    assert hashlib.sha256(Path(PACKAGE).read_bytes()).hexdigest() == expected
