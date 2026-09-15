from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import LlmMode
from app.main import app
from app.parsers.public322 import parse_public_profile_zip
from app.product.comparison import ComparisonManager
from app.product.explanation import explanation
from app.product.models import ComparisonRequest, DossierAnalysisRequest
from app.product.models_registry import ModelProfileRegistry, ProductConfigurationError
from app.product.repository import (
    ComparisonRunRepository,
    DossierRunRepository,
    InventoryRepository,
)
from app.product.services import DossierAnalysisManager
from app.product.verify_m422 import PACKAGE, _target
from fastapi.testclient import TestClient
from pydantic import ValidationError


def settings(**kwargs: Any) -> Settings:
    return Settings(**{"_env_file": None, **kwargs})


@pytest.mark.parametrize("request_type", [ComparisonRequest, DossierAnalysisRequest])
def test_request_model_override_is_forbidden(request_type: Any) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        request_type(inventory_id="inv-example", model_id="gpt-5.5", target_context=_target())


@pytest.mark.parametrize(
    "mode,endpoint,destination,expected",
    [
        ("fixture", None, "external_provider", "not_transmitted"),
        ("live", "https://api.openai.com/v1", "external_provider", "external_provider"),
        ("live", "http://127.0.0.1:8888/v1", "local_service", "local_service"),
        ("live", "https://example.com/v1", "local_service", "unavailable"),
        ("disabled", None, "external_provider", "unavailable"),
    ],
)
def test_validated_transmission_disclosure(
    mode: str,
    endpoint: str | None,
    destination: str,
    expected: str,
) -> None:
    registry = ModelProfileRegistry(
        settings(
            llm_mode=mode,
            llm_base_url=endpoint,
            llm_api_key="test-only",
            llm_model="gpt-5.5",
            product_evidence_destination=destination,
        )
    )
    config = registry.active_configuration()
    assert config.evidence_transmission == expected
    assert "test-only" not in config.model_dump_json()
    assert endpoint is None or endpoint not in config.model_dump_json()


@pytest.mark.parametrize("profile", ["unknown", "qwen3.6-local"])
def test_unavailable_active_profile_has_no_fallback(profile: str) -> None:
    registry = ModelProfileRegistry(settings(product_model_profile=profile))
    assert registry.active_configuration().availability != "available"
    with pytest.raises(ProductConfigurationError):
        registry.active()


def test_fingerprint_contains_execution_configuration_but_not_secrets() -> None:
    a = settings(
        llm_mode="live",
        llm_base_url="https://example.com/v1",
        llm_api_key="secret-a",
        llm_model="gpt-5.5",
    )
    b = a.model_copy(update={"llm_base_url": "https://other.example/v1"})
    c = a.model_copy(update={"llm_timeout_seconds": 30})
    digests = {ModelProfileRegistry(s).active().configuration_digest for s in (a, b, c)}
    assert len(digests) == 3


def manager_pair(registry: ModelProfileRegistry) -> tuple[Any, Any, str]:
    inventories = InventoryRepository(capacity=2, ttl_seconds=60)
    envelope = inventories.put(parse_public_profile_zip(PACKAGE.read_bytes()))
    dossier = DossierAnalysisManager(
        inventories=inventories,
        runs=DossierRunRepository(capacity=4, ttl_seconds=60, prefix="dossier"),
        registry=registry,
        settings=registry.settings,
    )
    comparison = ComparisonManager(
        inventories=inventories,
        runs=ComparisonRunRepository(capacity=4, ttl_seconds=60, prefix="comparison"),
        registry=registry,
        settings=registry.settings,
    )
    return dossier, comparison, envelope.inventory_id


def test_bound_configuration_survives_changes_for_all_systems_and_history() -> None:
    registry = ModelProfileRegistry(settings(llm_mode=LlmMode.FIXTURE))
    dossier, comparison, inventory_id = manager_pair(registry)
    request = ComparisonRequest(inventory_id=inventory_id, target_context=_target())
    run = comparison.create(request)
    dossier_run = dossier.create(
        DossierAnalysisRequest(
            inventory_id=inventory_id,
            target_context=_target(),
        )
    )
    registry.settings.product_model_profile = "unavailable-after-creation"
    asyncio.run(comparison.execute(run.comparison_id))
    asyncio.run(dossier.execute(dossier_run.run_id))
    completed = comparison.runs.get(run.comparison_id)
    assert completed.state == "completed"
    assert len(completed.results) == 12
    for cell in completed.results:
        assert cell.explanation is not None
        if cell.system == "B2":
            assert cell.model.attempt_count == 0
            assert cell.model.status == "not_applicable"
        else:
            assert cell.model.model_profile_id == "gpt-5.5"
            assert cell.model.configuration_digest == run.selected_model.configuration_digest
            assert cell.model.provider_reported_model_name is None
        if cell.system in {"B0", "B1"}:
            assert cell.explanation.findings is None
            assert cell.graph is None
            assert not cell.rule_ids
            assert {e.id for e in cell.explanation.evidence} == set(cell.evidence_ids)
        else:
            assert cell.explanation.repair is not None
            assert cell.explanation.uncertainty is not None
    assert dossier.runs.get(dossier_run.run_id).state == "completed"
    with pytest.raises(ProductConfigurationError):
        comparison.create(request)
    registry.settings.product_model_profile = "gpt-5.5"
    registry.settings.product_max_output_tokens += 1
    fresh = comparison.create(request)
    assert fresh.comparison_id != run.comparison_id
    assert comparison.runs.get(run.comparison_id) == completed


def test_construction_failure_terminates_without_fabricating_execution() -> None:
    class BrokenRegistry(ModelProfileRegistry):
        def create(self, model_id: str) -> Any:
            raise RuntimeError("construction failed")

    dossier, comparison, inventory_id = manager_pair(BrokenRegistry(settings()))
    d = dossier.create(DossierAnalysisRequest(inventory_id=inventory_id, target_context=_target()))
    c = comparison.create(ComparisonRequest(inventory_id=inventory_id, target_context=_target()))
    asyncio.run(dossier.execute(d.run_id))
    asyncio.run(comparison.execute(c.comparison_id))
    failed = dossier.runs.get(d.run_id)
    assert failed.state == "failed"
    assert not failed.results
    for failure in failed.failures:
        assert failure.model.attempt_count == 0
        assert failure.model.adapter_type == "not-executed"
        assert failure.model.provider_reported_model_name is None
    compared = comparison.runs.get(c.comparison_id)
    assert compared.state == "partial_failed"
    assert all(cell.system == "B2" for cell in compared.results if cell.decision)
    for cell in compared.results:
        if cell.system != "B2":
            assert cell.model.attempt_count == 0
            assert cell.model.provider_reported_model_name is None


def test_source_digest_mismatch_is_a_presentation_limitation() -> None:
    from app.standards.evidence import EvidenceRegistry

    span = EvidenceRegistry().load()[0].model_copy(update={"source_sha256": "a" * 64})
    projected = explanation(evidence=(span,))
    assert projected.evidence == (span,)
    assert not projected.sources
    assert any("identity/digest" in item for item in projected.limitations)


def test_active_configuration_api_and_override_rejection() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/config/product").status_code == 200
    for endpoint in ("dossier-analyses", "comparisons"):
        response = client.post(
            f"/api/v1/{endpoint}",
            json={
                "inventory_id": "inv-example",
                "model_id": "gpt-5.5",
                "target_context": _target().model_dump(mode="json"),
            },
        )
        assert response.status_code == 422


def test_real_adapter_with_mock_transport_keeps_attribution_across_systems_and_retry() -> None:
    from app.llm.responses import ResponsesStructuredModel

    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(503, json={"error": {"type": "service_unavailable"}})
        direct = "decision" in payload["text"]["format"]["schema"]["properties"]
        output = (
            {
                "decision": "HUMAN_REGULATORY_REVIEW",
                "severity": "unresolved",
                "action": "AUTHOR_REVIEW_HEADING_MAPPING",
                "human_review_required": True,
                "rationale": "The bounded evidence requires review.",
                "evidence_ids": [],
                "confidence": 0,
            }
            if direct
            else {
                "fixture_version": "1.0.0",
                "abstained": True,
                "abstain_reason": "Insufficient bounded evidence",
                "findings": [],
                "confidence": 0,
            }
        )
        return httpx.Response(
            200,
            json={
                "id": "resp_network_free_test",
                "status": "completed",
                "model": "gpt-5.5-reported-revision",
                "output_text": json.dumps(output),
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 100,
                    "output_tokens_details": {"reasoning_tokens": 20},
                },
            },
        )

    class MockTransportRegistry(ModelProfileRegistry):
        def create(self, model_id: str) -> ResponsesStructuredModel:
            model = super().create(model_id)
            assert isinstance(model, ResponsesStructuredModel)
            model.transport = httpx.MockTransport(handler)
            return model

    registry = MockTransportRegistry(
        settings(
            llm_mode="live",
            llm_model="gpt-5.5",
            llm_api_key="test-only",
            llm_base_url="https://provider.example/v1",
        )
    )
    _, manager, inventory_id = manager_pair(registry)
    run = manager.create(ComparisonRequest(inventory_id=inventory_id, target_context=_target()))
    registry.settings.llm_model = "must-not-be-used"
    asyncio.run(manager.execute(run.comparison_id))
    result = manager.runs.get(run.comparison_id)
    assert result.state == "completed"
    assert len(requests) == 10  # 3 documents x 3 model-assisted systems, plus one retry.
    assert {request["model"] for request in requests} == {"gpt-5.5"}
    assert result.results[0].model.attempt_count == 2
    for cell in result.results:
        if cell.system != "B2":
            assert cell.model.provider_reported_model_name == "gpt-5.5-reported-revision"
            assert cell.model.adapter_type == "responses"
            assert cell.model.configuration_digest == run.selected_model.configuration_digest


def test_frontend_contract_example_validates_against_real_product_schemas() -> None:
    from app.parsers.models import ApplicationInventory
    from app.product.models import ActiveProductConfiguration, ComparisonRun, DossierAnalysisRun

    fixture = json.loads(
        (REPOSITORY_ROOT / "frontend/src/test/fixtures/m43-product.json").read_text()
    )
    ApplicationInventory.model_validate(fixture["inventory"])
    ActiveProductConfiguration.model_validate(fixture["configuration"])
    DossierAnalysisRun.model_validate(fixture["run"])
    DossierAnalysisRun.model_validate(fixture["abstention"])
    ComparisonRun.model_validate(fixture["comparison"])


def test_b2_pipeline_failure_keeps_model_free_attribution(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.baselines.runner import OmittedSemanticModel
    from app.product import comparison

    original = comparison._pipeline_output

    async def fail_b2(**kwargs: Any) -> Any:
        if isinstance(kwargs["semantic_model"], OmittedSemanticModel):
            raise RuntimeError("bounded test failure")
        return await original(**kwargs)

    monkeypatch.setattr(comparison, "_pipeline_output", fail_b2)
    _, manager, inventory_id = manager_pair(ModelProfileRegistry(settings()))
    run = manager.create(ComparisonRequest(inventory_id=inventory_id, target_context=_target()))
    asyncio.run(manager.execute(run.comparison_id))
    failed = manager.runs.get(run.comparison_id)
    assert failed.state == "partial_failed"
    assert len(failed.failures) == 3
    assert all(item.model.model_profile_id == "model-free" for item in failed.failures)
    assert all(item.model.attempt_count == 0 for item in failed.failures)
    assert all(item.system != "B2" for item in failed.results)
