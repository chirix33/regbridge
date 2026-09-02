import json
from pathlib import Path

import pytest
from app.presentation import generate
from app.presentation.repository import SNAPSHOT_PATH, compute_snapshot_sha256, load_m4_snapshot


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk_strings(child)]
    if isinstance(value, str):
        return [value]
    return []


def test_snapshot_loads_and_preserves_m3_disclosures() -> None:
    snapshot = load_m4_snapshot()
    manifest = json.loads(
        (generate.SOURCE_RUN_DIR / "manifest.json").read_text(encoding="utf-8")
    )

    assert snapshot.source_run_id == "m3-live-phase2-20260901T170811002109Z"
    assert snapshot.predictions_sha256 == manifest["artifact_digests"]["predictions_sha256"]
    assert snapshot.metrics_sha256 == manifest["artifact_digests"]["metrics_sha256"]
    assert snapshot.frozen_prompt_digest == manifest["frozen_prompt_digest"]
    assert snapshot.frozen_configuration_digest == manifest["frozen_configuration_digest"]
    assert snapshot.current_fda_operational_availability == "not_operational"
    assert snapshot.expert_validated is False
    assert snapshot.eligible_for_performance_claims is True
    assert snapshot.completion_audit["integrity_audit_passed"] is True
    assert len(snapshot.cases) == 12
    assert {case.split for case in snapshot.cases} == {"test"}
    assert snapshot.snapshot_sha256 == compute_snapshot_sha256(snapshot)


def test_snapshot_excludes_raw_provider_and_prompt_material() -> None:
    snapshot_path = Path(SNAPSHOT_PATH)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rendered_strings = "\n".join(_walk_strings(payload)).casefold()

    prohibited = (
        "response_id",
        "resp_",
        "final_json_text",
        "request_digest",
        "api_key",
        "llm_api_key",
        "prompt",
        "reasoning",
        "c:\\",
    )
    for item in prohibited:
        assert item not in rendered_strings


def test_source_hash_mismatch_fails_before_snapshot_build(monkeypatch: pytest.MonkeyPatch) -> None:
    tampered = dict(generate.EXPECTED_SOURCE_HASHES)
    first_key = next(iter(tampered))
    tampered[first_key] = "0" * 64
    monkeypatch.setattr(generate, "EXPECTED_SOURCE_HASHES", tampered)

    with pytest.raises(ValueError, match="source artifact changed"):
        generate.build_snapshot()


def test_build_snapshot_is_byte_reproducible() -> None:
    first = generate.build_snapshot()
    second = generate.build_snapshot()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert compute_snapshot_sha256(first) == compute_snapshot_sha256(second)


def test_every_snapshot_metric_is_derived_from_phase2_metrics() -> None:
    """Independently project every presentation metric from the frozen metrics artifact."""
    snapshot = load_m4_snapshot()
    metrics = json.loads(
        (generate.SOURCE_RUN_DIR / "metrics.json").read_text(encoding="utf-8")
    )
    source_reports = {
        (item["system"], item["repetition_index"]): item["report"]
        for item in metrics["per_repetition_reports"]
    }
    source_reports[("B2", None)] = metrics["b2_report"]

    assert len(snapshot.metric_reports) == len(source_reports)
    for rendered in snapshot.metric_reports:
        source = source_reports[(rendered.system, rendered.repetition_index)]
        expected_invalid = (
            {"invalid_outputs": 0, "failure_rate": 0.0}
            if rendered.repetition_index is None or rendered.system == "B2"
            else metrics["invalid_output_diagnostics"][str(rendered.repetition_index)][
                rendered.system
            ]
        )
        expected = {
            "system": source["system"],
            "repetition_index": rendered.repetition_index,
            "result_status": source["result_status"],
            "accuracy": source["accuracy"],
            "macro_f1": source["macro_f1"],
            "unsafe_false_negative_rate": {
                key: source["unsafe_false_negative_rate"][key]
                for key in ("numerator", "denominator", "rate")
            },
            "review_bypass_rate": {
                key: source["review_bypass_rate"][key]
                for key in ("numerator", "denominator", "rate")
            },
            "outside_represented_rate": source["vocabulary_diagnostic"][
                "outside_represented_rate"
            ],
            "invalid_outputs": expected_invalid["invalid_outputs"],
            "invalid_output_rate": expected_invalid["failure_rate"],
            "requests": source["requests"],
            "input_tokens": source["input_tokens"],
            "output_tokens": source["output_tokens"],
            "latency_ms_total": source["latency_ms_total"],
            "cost_usd": source.get("cost_usd"),
            "retrieval": source.get("retrieval"),
            "family_sensitivity": source.get("family_sensitivity") or [],
        }
        assert rendered.model_dump(mode="json") == expected

    assert snapshot.metric_ranges == metrics["metric_ranges"]
    expected_retrieval = [
        {
            "repetition_index": item["repetition_index"],
            "recall_at_3": item["report"]["retrieval"]["recall_at_3"],
            "precision_at_3": item["report"]["retrieval"]["precision_at_3"],
            "mrr": item["report"]["retrieval"]["mrr"],
            "evaluated_cases": item["report"]["retrieval"]["evaluated_cases"],
        }
        for item in metrics["per_repetition_reports"]
        if item["system"] == "B1"
    ]
    assert snapshot.retrieval_summary == {
        "result_status": "genuine deterministic retrieval measurement",
        "per_repetition": expected_retrieval,
    }


def test_non_metric_dashboard_summaries_are_derived_from_completion_audit() -> None:
    snapshot = load_m4_snapshot()
    audit = json.loads(
        (generate.SOURCE_RUN_DIR / "completion-audit.json").read_text(encoding="utf-8")
    )

    assert snapshot.completion_audit == {
        "state": audit["state"],
        "stop_reason": audit["stop_reason"],
        "integrity_audit_passed": audit["integrity_audit_passed"],
        "scheduled_outcomes": audit["scheduled_outcomes"],
        "completed_outcomes": audit["completed_outcomes"],
        "truncation_count": audit["truncation_count"],
    }
    assert snapshot.usage_summary == audit["usage"]["overall"]
    assert snapshot.cost_summary == {
        "total_cost_usd": audit["usage"]["total_cost_usd"],
        "unknown_cost_outcomes": audit["usage"]["unknown_cost_outcomes"],
    }
