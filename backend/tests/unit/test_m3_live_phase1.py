import json
from typing import Any

import httpx
import pytest
from app.evaluation.live_phase1 import (
    LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
    LIVE_INPUT_CHARACTER_LIMIT,
    LIVE_PILOT_OUTPUT_CEILING,
    LivePhase1Error,
    _phase2_cap,
    _score_valid,
    _token_counter,
)
from app.evaluation.phase1_bundle import build_phase1_bundle
from app.llm.models import ModelRequest, SemanticRiskOutput
from app.llm.responses import ResponsesStructuredModel, _strict_json_schema
from app.standards.evidence import EvidenceRegistry


def test_phase1_export_contains_only_train_development_inputs() -> None:
    bundle = build_phase1_bundle()
    assert len(bundle.cases) == 18
    assert len(bundle.case_inputs) == 18
    assert sum(case.split == "train" for case in bundle.cases) == 12
    assert sum(case.split == "development" for case in bundle.cases) == 6
    assert {case.split for case in bundle.cases} == {"train", "development"}
    assert all(case.expert_validated is False for case in bundle.cases)
    assert bundle.operational_availability == "not_operational"
    assert set(bundle.selected_input_hashes) == {case.case_id for case in bundle.cases}


def test_phase1_case_input_serialization_excludes_reference_labels() -> None:
    bundle = build_phase1_bundle()
    serialized = json.dumps(
        [case_input.model_dump(mode="json") for case_input in bundle.case_inputs],
        sort_keys=True,
    )
    for case in bundle.cases:
        assert case.reference.rationale not in serialized
        assert case.reference.decision.value not in serialized
        for rule_id in case.reference.required_rule_ids:
            assert rule_id not in serialized


@pytest.mark.asyncio
async def test_responses_adapter_records_reasoning_temperature_and_final_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["reasoning"]["effort"] == "medium"
        assert payload["temperature"] == 0
        assert payload["max_output_tokens"] == LIVE_PILOT_OUTPUT_CEILING
        response_text = json.dumps(
            {
                "fixture_version": "1.0.0",
                "abstained": False,
                "abstain_reason": None,
                "findings": [],
                "confidence": 1,
            }
        )
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "status": "completed",
                "model": "gpt-5.5-2026-04-23",
                "temperature": 0,
                "output_text": response_text,
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 25},
                    "output_tokens": 140,
                    "output_tokens_details": {"reasoning_tokens": 120},
                },
            },
        )

    model = ResponsesStructuredModel(
        base_url="https://api.openai.example/v1",
        api_key="redacted",
        model="gpt-5.5",
        timeout_seconds=1,
        count_final_tokens=lambda text: len(text.split()),
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(
        fixture_lookup_key="fixture-hidden",
        task="Inspect evidence.",
        context={"authority": "FDA"},
        evidence=(),
        prompt_template_version="1.0.0",
    )
    completion = await model.complete(request, SemanticRiskOutput)
    assert completion.output.confidence == 1
    attempt = model.last_attempts[0]
    assert attempt.temperature_verification == "reported_match"
    assert attempt.reasoning_tokens == 120
    assert attempt.cached_input_tokens == 25
    assert attempt.total_output_tokens == 140


@pytest.mark.asyncio
async def test_responses_adapter_rejects_final_answer_token_overrun() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "temperature": 0,
                "output_text": json.dumps(
                    {
                        "fixture_version": "1.0.0",
                        "abstained": False,
                        "abstain_reason": None,
                        "findings": [],
                        "confidence": 1,
                    }
                ),
                "usage": {"output_tokens": 1},
            },
        )

    model = ResponsesStructuredModel(
        base_url="https://api.openai.example/v1",
        api_key="redacted",
        model="gpt-5.5",
        timeout_seconds=1,
        count_final_tokens=lambda _: LIVE_FINAL_SCHEMA_TOKEN_LIMIT + 1,
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(
        fixture_lookup_key="fixture-hidden",
        task="Inspect evidence.",
        context={"authority": "FDA"},
        evidence=(),
        prompt_template_version="1.0.0",
    )
    with pytest.raises(Exception, match="live response invalid"):
        await model.complete(request, SemanticRiskOutput)
    assert model.last_attempts[0].status == "failed"


def test_score_valid_excludes_invalid_outputs_from_decision_metrics() -> None:
    bundle = build_phase1_bundle()
    report, cases = _score_valid(
        cases=bundle.cases[:1],
        predictions=(),
        retrieval_traces=(),
        scope="phase1-train",
        seed=20270829,
    )
    assert report is None
    assert cases == ()


def test_phase2_cap_is_precommitted_and_withheld_for_missing_usage() -> None:
    assert _phase2_cap(()) == {
        "status": "withheld",
        "reason": "reasoning token usage was not reported",
    }


def test_tokenizer_dependency_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> object:
        if name == "tiktoken":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(LivePhase1Error, match="tiktoken is required"):
        _token_counter("gpt-5.5")


def test_model_facing_input_limit_is_enforced_before_dispatch() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    model = ResponsesStructuredModel(
        base_url="https://api.openai.example/v1",
        api_key="redacted",
        model="gpt-5.5",
        timeout_seconds=1,
        count_final_tokens=lambda text: len(text.split()),
        input_character_limit=LIVE_INPUT_CHARACTER_LIMIT,
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(
        fixture_lookup_key="fixture-hidden",
        task="x" * LIVE_INPUT_CHARACTER_LIMIT,
        context={},
        evidence=(),
        prompt_template_version="1.0.0",
    )
    with pytest.raises(Exception, match="exceeded"):
        import asyncio

        asyncio.run(model.complete(request, SemanticRiskOutput))
    assert called is False


def test_evidence_registry_still_has_six_ordered_source_spans() -> None:
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    assert len(evidence) == 6


def test_responses_schema_is_strict_for_optional_fields() -> None:
    schema = _strict_json_schema(SemanticRiskOutput.model_json_schema())
    assert "default" not in json.dumps(schema)
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
