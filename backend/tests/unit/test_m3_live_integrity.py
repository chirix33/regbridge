"""Synthetic responses and isolated train/dev inputs only; never load held-out data."""

import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from app.analyzer.service import AnalysisPipelineError
from app.config import Settings
from app.domain.enums import LlmMode
from app.evaluation import live_configuration as config
from app.evaluation import live_phase1 as live
from app.evaluation import live_phase2 as phase2
from app.evaluation.metrics import score_system
from app.evaluation.models import DirectDecisionOutput, SystemName, SystemPrediction
from app.evaluation.phase1_bundle import load_phase1_bundle
from app.llm.models import SemanticRiskOutput
from app.llm.responses import LiveModelInvalidOutput, ResponsesStructuredModel


@pytest.mark.parametrize("key", [
    "direct_schema", "semantic_schema", "direct_prompt", "semantic_prompt", "serializer",
    "reasoning_effort", "max_output_tokens", "final_structured_answer_token_limit",
    "temperature_handling", "system_instructions", "input_character_limit", "retry_limit",
    "shared_output_vocabulary", "action_vocabulary_disclosure", "b2_scoring_contract_source",
    "retry_policy", "graph_contract", "graph_enums_source", "graph_models_source",
    "graph_builder_source", "analysis_pipeline_source", "analysis_repository_source",
    "live_retry_and_summary_source", "semantic_serializer", "held_out_bundle_source",
    "phase2_b2_source", "phase2_runner_source",
])
def test_every_configuration_change_aborts_before_any_heldout_operation(
    key: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = config.configuration_material(max_output_tokens=4000)
    frozen = config.content_digest(original)
    gate = config.HeldOutApprovalGate(
        "author-01", config.content_digest(config.template_digests(original)), frozen, 4000,
    )
    assert gate.before_loading(lambda: "synthetic-loader") == "synthetic-loader"
    changed = copy.deepcopy(original)
    changed[key] = {"changed": changed[key]}
    assert config.content_digest(changed) != frozen
    monkeypatch.setattr(config, "configuration_material", lambda **_: changed)
    for boundary in (gate.before_loading, gate.before_repetition, gate.before_dispatch):
        with pytest.raises(ValueError, match="aborted.*configuration digest mismatch"):
            boundary(lambda: pytest.fail("must reject before loading or dispatch"))


def test_actual_direct_schema_mutation_changes_template_and_configuration_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = config.configuration_material()
    original = DirectDecisionOutput.model_json_schema()
    original["properties"]["action"]["description"] = "synthetic schema mutation"
    monkeypatch.setattr(DirectDecisionOutput, "model_json_schema", lambda: original)
    after = config.configuration_material()
    assert config.template_digests(before)["direct_schema"] != (
        config.template_digests(after)["direct_schema"]
    )
    assert config.content_digest(before) != config.content_digest(after)


def test_phase2_prepare_publishes_freeze_manifest_without_loading_heldout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = config.configuration_material(max_output_tokens=4000)
    gate = config.HeldOutApprovalGate(
        author_id="author-01",
        frozen_prompt_digest=config.content_digest(config.template_digests(material)),
        frozen_configuration_digest=config.content_digest(material),
        max_output_tokens=4000,
    )
    monkeypatch.setattr(phase2, "load_phase2_approval_gate", lambda: gate)
    monkeypatch.setattr(phase2, "PHASE2_RESULTS_ROOT", tmp_path / "results" / "live")
    monkeypatch.setattr(phase2, "PHASE2_PAPER_ROOT", tmp_path / "paper" / "tables" / "live")
    monkeypatch.setattr(
        phase2, "write_phase2_bundle",
        lambda: pytest.fail("prepare must not load or export the held-out split"),
    )
    path = phase2.prepare_phase2_run()
    manifest = json.loads((path / "manifest.pre-run.json").read_text())
    assert manifest["state"] == "prepared"
    assert manifest["benchmark"]["held_out_loaded_at_manifest_creation"] is False
    assert manifest["frozen_prompt_digest"] == gate.frozen_prompt_digest
    assert manifest["frozen_configuration_digest"] == gate.frozen_configuration_digest
    assert manifest["model_configuration"]["max_output_tokens"] == 4000
    assert manifest["model_configuration"]["final_structured_answer_token_limit"] == 800
    assert set(manifest["freeze_component_digests"]) == {
        "direct_output_schema", "semantic_output_schema", "direct_prompt_template",
        "semantic_prompt_template", "system_instructions", "direct_serializer",
        "semantic_serializer", "action_vocabulary_packet_and_definitions", "graph_contract",
        "reasoning_effort", "max_output_tokens", "structured_answer_token_limit",
        "input_character_limit", "temperature_handling", "retry_policy",
    }


@pytest.mark.asyncio
async def test_frozen_dispatch_mismatch_is_nonretryable_and_makes_no_request() -> None:
    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test-secret", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 10,
        transport=httpx.MockTransport(
            lambda _: pytest.fail("frozen mismatch must abort before provider dispatch")
        ),
    )
    with pytest.raises(config.HeldOutConfigurationMismatch):
        await live._retry_live_call(
            model=model,
            first_authorized_request=False,
            dispatch_guard=lambda: (_ for _ in ()).throw(
                config.HeldOutConfigurationMismatch("synthetic frozen mutation")
            ),
            call=lambda: model.complete_text(
                input_text="synthetic",
                output_type=SemanticRiskOutput,
                prompt_template_version="synthetic",
            ),
        )
    assert model.last_attempts == ()


@pytest.mark.asyncio
async def test_phase2_schedules_three_separate_repetitions_and_no_complete_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_phase1_bundle()
    cases = tuple(case.model_copy(update={"split": "test"}) for case in source.cases[:12])
    bundle = SimpleNamespace(
        cases=cases,
        case_inputs=source.case_inputs[:12],
        fixture_metadata=source.fixture_metadata,
    )
    material = config.configuration_material(max_output_tokens=4000)
    gate = config.HeldOutApprovalGate(
        "author-01",
        config.content_digest(config.template_digests(material)),
        config.content_digest(material),
        4000,
    )
    monkeypatch.setattr(phase2, "load_phase2_approval_gate", lambda: gate)
    monkeypatch.setattr(
        phase2, "_load_prepared_manifest",
        lambda *_: {"model_configuration": {}, "run_id": "synthetic"},
    )
    monkeypatch.setattr(phase2, "write_phase2_bundle", lambda: bundle)
    monkeypatch.setattr(phase2, "load_phase2_bundle", lambda: bundle)
    monkeypatch.setattr(phase2, "_settings", lambda: SimpleNamespace(llm_model="gpt-5.5"))
    monkeypatch.setattr(phase2, "_token_counter", lambda _: ("synthetic", lambda _: []))
    monkeypatch.setattr(phase2, "_phase2_model", lambda *_: SimpleNamespace())

    async def fake_b2(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace()

    async def outcome_for(system: str, case: Any) -> live.LiveOutcome:
        system_name = cast(SystemName, system)
        prediction = SystemPrediction(
            system=system_name,
            case_id=case.case_id,
            decision=case.reference.decision,
            severity=case.reference.severity,
            action=case.reference.action,
            human_review_required=case.reference.human_review_required,
            unconditional_reuse=False,
            rationale="Synthetic held-out scheduler validation.",
            evidence_ids=(),
            rule_ids=(),
            confidence=0.5,
            prediction_source=(
                "live_hybrid_model" if system == "RegBridge" else "live_direct_model"
            ),
            empirical_model_observation=True,
            latency_ms=0,
            requests=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0,
        )
        return live.LiveOutcome(
            system=system_name,
            case_id=case.case_id,
            split="test",
            outcome="valid_prediction",
            prediction=prediction,
            retrieval=None,
            attempts=(),
            deviation_log=(),
            failure=None,
        )

    async def fake_direct(**kwargs: Any) -> live.LiveOutcome:
        return await outcome_for(kwargs["system"], kwargs["case"])

    async def fake_regbridge(**kwargs: Any) -> live.LiveOutcome:
        return await outcome_for("RegBridge", kwargs["case"])

    monkeypatch.setattr(phase2, "rescore_phase2_b2", fake_b2)
    monkeypatch.setattr(phase2, "_run_direct", fake_direct)
    monkeypatch.setattr(phase2, "_run_regbridge", fake_regbridge)
    writes: list[tuple[str, int]] = []

    def fake_write(**kwargs: Any) -> Path:
        writes.append((kwargs["state"], len(kwargs["outcomes"])))
        return tmp_path

    monkeypatch.setattr(phase2, "_write_artifacts", fake_write)
    result = await phase2.execute_phase2("m3-live-phase2-20260901T000000000000Z")
    assert result == tmp_path
    assert writes[-1] == ("completed", 108)
    assert ("running", 108) not in writes
    assert sum(state == "running" for state, _ in writes) == 108


def test_phase2_terminal_artifacts_are_complete_and_claim_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = load_phase1_bundle()
    cases = tuple(case.model_copy(update={"split": "test"}) for case in source.cases[:12])
    bundle = SimpleNamespace(cases=cases)
    inputs = {item.case_id: item for item in source.case_inputs[:12]}
    evidence = tuple(sorted(phase2.EvidenceRegistry().load(), key=lambda item: item.id))
    retriever = phase2.BM25Retriever(evidence)
    outcomes: list[phase2.RepetitionOutcome] = []
    for repetition in range(1, 4):
        for system in ("B0", "B1", "RegBridge"):
            system_name = cast(SystemName, system)
            for case in cases:
                prediction = SystemPrediction(
                    system=system_name,
                    case_id=case.case_id,
                    decision=case.reference.decision,
                    severity=case.reference.severity,
                    action=cast(Any, case.reference.action),
                    human_review_required=case.reference.human_review_required,
                    unconditional_reuse=False,
                    rationale="Synthetic terminal artifact validation.",
                    evidence_ids=(),
                    rule_ids=(),
                    confidence=0.5,
                    prediction_source=(
                        "live_hybrid_model" if system == "RegBridge" else "live_direct_model"
                    ),
                    empirical_model_observation=True,
                    latency_ms=0,
                    requests=0,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0,
                )
                outcomes.append(phase2.RepetitionOutcome(
                    repetition,
                    live.LiveOutcome(
                        system=system_name,
                        case_id=case.case_id,
                        split="test",
                        outcome="valid_prediction",
                        prediction=prediction,
                        retrieval=(
                            retriever.retrieve(
                                case_id=case.case_id,
                                query=json.dumps(inputs[case.case_id].material, sort_keys=True),
                            )
                            if system == "B1" else None
                        ),
                        attempts=(),
                        deviation_log=(),
                        failure=None,
                    ),
                ))
    b2_predictions = tuple(
        SystemPrediction(
            system="B2",
            case_id=case.case_id,
            decision=case.reference.decision,
            severity=case.reference.severity,
            action=cast(Any, case.reference.action),
            human_review_required=case.reference.human_review_required,
            unconditional_reuse=False,
            rationale="Synthetic B2 artifact validation.",
            prediction_source="genuine_rule_only",
            empirical_model_observation=False,
            latency_ms=0,
            requests=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0,
        ) for case in cases
    )
    b2_report, _ = score_system(
        cases=cases,
        predictions=b2_predictions,
        retrieval_traces=(),
        scope="held-out-test",
        seed=1,
        regulatory_evidence_ids=frozenset(),
    )
    b2 = SimpleNamespace(
        report=b2_report,
        artifact=lambda: {
            "predictions": [item.model_dump(mode="json") for item in b2_predictions]
        },
    )
    monkeypatch.setattr(phase2, "PHASE2_RESULTS_ROOT", tmp_path / "results" / "live")
    monkeypatch.setattr(phase2, "PHASE2_PAPER_ROOT", tmp_path / "paper" / "tables" / "live")
    monkeypatch.setattr(phase2, "phase2_bundle_sha256", lambda: "f" * 64)
    monkeypatch.setattr(
        phase2,
        "PHASE2_BUNDLE",
        phase2.REPOSITORY_ROOT / "data/benchmark/phase2/absent-test-bundle.json",
    )
    prepared = {
        "run_id": "m3-live-phase2-20260901T000000000000Z",
        "state": "prepared",
        "eligible_for_performance_claims": False,
        "frozen_prompt_digest": "a" * 64,
        "frozen_configuration_digest": "b" * 64,
    }
    path = phase2._write_artifacts(
        run_id=cast(str, prepared["run_id"]),
        prepared=prepared,
        bundle=cast(Any, bundle),
        outcomes=tuple(outcomes),
        b2=cast(Any, b2),
        state="completed",
        stop_reason="completed_without_failure",
    )
    manifest = json.loads((path / "manifest.json").read_text())
    metrics = json.loads((path / "metrics.json").read_text())
    audit = json.loads((path / "completion-audit.json").read_text())
    assert manifest["progress"]["completed_outcomes"] == 108
    assert len(manifest["per_repetition_reports"]) == 9
    assert manifest["eligible_for_performance_claims"] is True
    assert metrics["eligible_for_performance_claims"] is True
    assert audit["integrity_audit_passed"] is True
    assert "| B2 | once |" in (path / "summary.md").read_text()


def test_phase1_claim_flags_and_deviations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", tmp_path / "results" / "live")
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper" / "tables" / "live")
    path = live._write_artifacts(
        bundle=load_phase1_bundle(), tokenizer_name="synthetic-counter", outcomes=(),
        stopped_reason="synthetic-test",
    )
    for artifact in (path / "manifest.json", path / "metrics.json"):
        value = json.loads(artifact.read_text())
        assert value["eligible_for_performance_claims"] is False
        assert value["empirical_model_run"] is True
        assert value["current_fda_operational_availability"] == "not_operational"
        assert value["expert_validated"] is False
        assert "temperature_requested" not in artifact.read_text()
    manifest = json.loads((path / "manifest.json").read_text())
    assert len(manifest["deviation_log"]) == 2
    assert manifest["deviation_log"][1]["observed_api_evidence"]["error_param"] == "temperature"
    assert {"direct_schema", "semantic_schema"} <= set(manifest["prompt_template_digests"])
    assert manifest["digests"]["configuration_sha256"] == config.content_digest(
        manifest["configuration_material"]
    )


def test_failed_audit_cannot_have_null_stop_or_phase2_proposal() -> None:
    common = {
        "state": "failed",
        "audit_passed": False,
        "regbridge_metrics_status": "withheld_until_all_18_outcomes_complete",
        "cross_system_comparison_status": "prohibited_failed_or_incomplete_audit",
    }
    with pytest.raises(live.LivePhase1Error, match="non-null stop reason"):
        live.RunAuditState(
            **common, stop_reason="",  # type: ignore[arg-type]
            phase2_cap_proposal={"status": "withheld"},
        )
    with pytest.raises(live.LivePhase1Error, match="cannot coexist"):
        live.RunAuditState(
            **common, stop_reason="audit_failed",  # type: ignore[arg-type]
            phase2_cap_proposal={"status": "proposed_requires_author_01_approval"},
        )


def test_summary_reports_recorded_b2_rescore_without_withheld_contradiction() -> None:
    manifest = {
        "run_id": "synthetic-complete",
        "state": "awaiting_author_01_approval",
        "stop_reason": "completed_without_failure",
        "regbridge_metrics_status": "complete",
        "cross_system_comparison_status": "complete_development_only",
        "progress": {
            "completed_outcomes": 54,
            "scheduled_outcomes": 54,
            "terminal_audit_complete": True,
        },
        "b2_rescore": {"artifact": "b2-contract-rescore.json"},
        "usage_summary": {
            system: {
                "attempts": 0,
                "reasoning_tokens_min": None,
                "reasoning_tokens_median": None,
                "reasoning_tokens_p95": None,
                "reasoning_tokens_max": None,
                "ceiling_hit_count": 0,
                "cost_usd": 0,
            }
            for system in live.LIVE_SYSTEMS
        },
        "phase2_cap_proposal": {"status": "withheld"},
    }
    summary = live._summary_markdown(manifest, (), ())
    assert "matching fresh B2 rescore is recorded" in summary
    assert "RegBridge completed all 18 development outcomes" in summary
    assert "RegBridge decision metrics are withheld" not in summary


def test_running_summary_reports_actual_progress_and_pending_terminal_audit() -> None:
    manifest = {
        "run_id": "synthetic-running",
        "state": "running",
        "stop_reason": "run_in_progress",
        "regbridge_metrics_status": "withheld_until_all_18_outcomes_complete",
        "cross_system_comparison_status": "prohibited_incomplete_system_coverage",
        "progress": {
            "completed_outcomes": 7,
            "scheduled_outcomes": 54,
            "terminal_audit_complete": False,
        },
        "usage_summary": {
            system: {
                "attempts": 0,
                "reasoning_tokens_min": None,
                "reasoning_tokens_median": None,
                "reasoning_tokens_p95": None,
                "reasoning_tokens_max": None,
                "ceiling_hit_count": 0,
                "cost_usd": 0,
            }
            for system in live.LIVE_SYSTEMS
        },
        "phase2_cap_proposal": {"status": "withheld"},
    }
    summary = live._summary_markdown(manifest, (), ())
    assert "Recorded 7/54 system-case outcomes" in summary
    assert "Terminal audit is pending" in summary
    assert "Recorded 54/54" not in summary


def response_body() -> dict[str, Any]:
    return {
        "status": "completed", "model": "gpt-5.5",
        "output_text": json.dumps({
            "fixture_version": "1.0.0", "abstained": False, "abstain_reason": None,
            "findings": [], "confidence": 0.5,
        }),
        "usage": {
            "input_tokens": 100, "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 900, "output_tokens_details": {"reasoning_tokens": 800},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["refusal", "schema_validation", "incomplete_response"])
async def test_schema_refusal_and_incomplete_fail_without_retry_or_decision(failure: str) -> None:
    payloads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(request.content)
        body = response_body()
        if failure == "refusal":
            body["output"] = [{"content": [{"type": "refusal", "refusal": "synthetic"}]}]
        elif failure == "schema_validation":
            body["output_text"] = '{"unknown_field": true}'
        else:
            body["status"] = "incomplete"
            body["incomplete_details"] = {"reason": "max_output_tokens"}
        return httpx.Response(200, json=body)

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test-secret", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50, transport=httpx.MockTransport(handler),
    )
    attempts, output, _ = await live._retry_live_call(
        model=model, first_authorized_request=False,
        call=lambda: model.complete_text(
            input_text="synthetic evidence", output_type=SemanticRiskOutput,
            prompt_template_version="1.0.0",
        ),
    )
    assert output is None
    assert len(attempts) == 1
    assert len(payloads) == 1
    assert "temperature" not in json.loads(payloads[0])
    assert attempts[0].cause == failure
    assert attempts[0].retryable is False
    assert all("test-secret" not in json.dumps(item.to_json()) for item in attempts)
    assert not [item for item in live._deviations(attempts) if item["type"] == "retry"]


@pytest.mark.asyncio
async def test_transport_and_api_failures_only_receive_bounded_retries() -> None:
    payloads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(request.content)
        return httpx.Response(503, json={"error": {
            "type": "server_error", "code": "temporarily_unavailable", "param": None,
        }})

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test-secret", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50, transport=httpx.MockTransport(handler),
    )
    attempts, output, failure = await live._retry_live_call(
        model=model, first_authorized_request=False,
        call=lambda: model.complete_text(
            input_text="synthetic evidence", output_type=SemanticRiskOutput,
            prompt_template_version="1.0.0",
        ),
    )
    assert output is None and failure == "api_failure"
    assert len(attempts) == len(payloads) == 3
    assert len(set(payloads)) == 1
    assert all(item.retryable and item.cause == "api_failure" for item in attempts)
    assert [item["cause"] for item in live._deviations(attempts)
            if item["type"] == "retry"] == ["api_failure", "api_failure"]


@pytest.mark.asyncio
async def test_deterministic_branch_does_not_reuse_previous_attempts() -> None:
    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_body())),
    )
    await model.complete_text(
        input_text="synthetic", output_type=SemanticRiskOutput, prompt_template_version="1.0.0",
    )
    assert model.last_attempts

    async def deterministic() -> str:
        return "synthetic deterministic output"

    attempts, result, _ = await live._retry_live_call(
        model=model, call=deterministic, first_authorized_request=False,
    )
    assert attempts == ()
    assert result == "synthetic deterministic output"


@pytest.mark.asyncio
async def test_downstream_persistence_failure_is_nonretryable_and_auditable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.content)
        return httpx.Response(200, json=response_body())

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50,
        transport=httpx.MockTransport(handler),
    )

    async def completes_then_persistence_fails() -> Any:
        await model.complete_text(
            input_text="synthetic", output_type=SemanticRiskOutput,
            prompt_template_version="1.0.0",
        )
        raise AnalysisPipelineError("persistence", ValueError("must remain redacted"))

    attempts, output, failure = await live._retry_live_call(
        model=model, call=completes_then_persistence_fails, first_authorized_request=False,
    )
    assert output is None
    assert len(requests) == len(attempts) == 1
    assert failure == "non_retryable_persistence:AnalysisPipelineError"
    assert attempts[0].status == "failed"
    assert attempts[0].cause == failure
    assert attempts[0].retryable is False

    bundle = load_phase1_bundle()
    case = bundle.cases[0]
    outcome = live.LiveOutcome(
        "RegBridge", case.case_id, case.split, "invalid_output", None, None,
        attempts, live._deviations(attempts), failure,
    )
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", tmp_path / "results/live")
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper/tables/live")
    result = live._write_artifacts(
        bundle=bundle, tokenizer_name="synthetic", outcomes=(outcome,),
        stopped_reason=failure,
    )
    row = (result / "per-case.csv").read_text(encoding="utf-8")
    assert "invalid_output" in row and failure in row


def test_null_retry_cause_is_rejected_before_any_artifact_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = response_body()
    attempt = live.ResponsesAttempt(
        attempt_index=1,
        request_digest="0" * 64,
        status="failed",
        cause=None,
        retryable=True,
        http_status=503,
        error_type="server_error",
        error_code="temporary",
        error_param=None,
        model_requested="gpt-5.5",
        model_reported=None,
        temperature_handling="unsupported_by_endpoint_parameter",
        reasoning_effort="medium",
        max_output_tokens=25_000,
        input_tokens=body["usage"]["input_tokens"],
        cached_input_tokens=0,
        final_answer_tokens=None,
        reasoning_tokens=800,
        total_output_tokens=900,
        finish_reason=None,
        response_status="failed",
        latency_ms=1,
        ceiling_hit=False,
        response_id=None,
    )
    case = load_phase1_bundle().cases[0]
    outcome = live.LiveOutcome(
        "B0", case.case_id, case.split, "invalid_output", None, None,
        (attempt,), (), "synthetic_failure",
    )
    root = tmp_path / "results/live"
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", root)
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper/tables/live")
    with pytest.raises(live.LivePhase1Error, match="null cause"):
        live._write_artifacts(
            bundle=load_phase1_bundle(), tokenizer_name="synthetic", outcomes=(outcome,),
            stopped_reason="synthetic_failure",
        )
    assert not root.exists()


@pytest.mark.asyncio
async def test_usage_cap_and_cost_include_failed_attempts() -> None:
    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 801,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response_body())),
    )
    with pytest.raises(LiveModelInvalidOutput):
        await model.complete_text(
            input_text="synthetic", output_type=SemanticRiskOutput,
            prompt_template_version="1.0.0",
        )
    outcome = live.LiveOutcome(
        "B0", "synthetic", "train", "invalid_output", None, None, model.last_attempts, (),
        "final_answer_token_limit",
    )
    assert model.last_attempts[0].final_answer_tokens == 801
    assert live._cost(model.last_attempts) == pytest.approx(0.02741)
    assert live._phase2_cap((outcome,))["phase2_cap"] == 4000
    missing = replace(model.last_attempts[0], reasoning_tokens=None, input_tokens=None)
    assert live._cost((missing,)) is None
    assert live._phase2_cap((replace(outcome, attempts=(*model.last_attempts, missing)),))[
        "status"
    ] == "withheld"
    summary = live._usage_summary((outcome,))
    assert summary["B0"]["reasoning_tokens_p95"] == 800
    assert summary["B1"]["reasoning_tokens_max"] is None


@pytest.mark.asyncio
async def test_phase_stops_after_new_failure_without_advancing_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "require_development_approval", lambda: None)
    requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.content)
        return httpx.Response(400, json={"error": {
            "type": "invalid_request_error", "code": "new_synthetic_error", "param": "text",
        }})

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50, transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(live, "_settings", lambda: Settings(llm_mode=LlmMode.FIXTURE))
    monkeypatch.setattr(live, "_token_counter", lambda _: ("synthetic", lambda _: [1]))
    monkeypatch.setattr(live, "_model", lambda *_: model)
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", tmp_path / "results" / "live")
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper" / "tables" / "live")
    path = await live.run_phase1_live()
    manifest = json.loads((path / "manifest.json").read_text())
    assert len(requests) == 3
    assert len(set(requests)) == 1
    stop_reason = manifest.get("stop_reason")
    if stop_reason != "api_failure":
        raise AssertionError((path, stop_reason, sorted(manifest)))
    assert manifest["state"] == "failed"
    assert manifest["integrity_audit"]["passed"] is False
    assert manifest["phase2_cap_proposal"]["status"] == "withheld"
    assert len((path / "predictions.jsonl").read_text().splitlines()) == 1
    metrics = json.loads((path / "metrics.json").read_text())
    assert metrics["reports"] == []
    assert metrics["invalid_output_counts"]["B0"]["valid_cases"] == 0
    assert metrics["invalid_output_counts"]["B1"]["not_run_cases"] == 18
