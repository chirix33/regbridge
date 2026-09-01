"""Frozen M3 held-out live evaluation with three separate model repetitions."""

import argparse
import asyncio
import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import SecretStr

from app.analyzer.prompts import SEMANTIC_INSPECTION_PROMPT_VERSION
from app.baselines.prompts import DIRECT_DECISION_PROMPT_VERSION
from app.baselines.retrieval import BM25Retriever
from app.config import REPOSITORY_ROOT, Settings
from app.evaluation.live_configuration import (
    PHASE2_MAX_OUTPUT_TOKENS,
    PHASE2_REPETITIONS,
    HeldOutApprovalGate,
    HeldOutConfigurationMismatch,
    configuration_material,
    content_digest,
    load_phase2_approval_gate,
    phase2_freeze_components,
    template_digests,
)
from app.evaluation.live_phase1 import (
    LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
    LIVE_INPUT_CHARACTER_LIMIT,
    LIVE_REASONING_EFFORT,
    LIVE_RETRY_LIMIT,
    LIVE_SEED,
    LIVE_SYSTEMS,
    PRICING_PER_MILLION,
    LiveOutcome,
    _atomic_write,
    _cost,
    _digest_bytes,
    _run_direct,
    _run_regbridge,
    _settings,
    _token_counter,
    _usage_summary,
    _validate_outcomes_for_write,
)
from app.evaluation.metrics import score_system
from app.evaluation.models import BenchmarkCase, CaseEvaluation, SystemPrediction
from app.evaluation.phase2_b2 import Phase2B2Rescore, rescore_phase2_b2
from app.evaluation.phase2_bundle import (
    PHASE2_BUNDLE,
    PHASE2_CASE_COUNT,
    Phase2Bundle,
    load_phase2_bundle,
    phase2_bundle_sha256,
    write_phase2_bundle,
)
from app.llm.responses import TEMPERATURE_HANDLING, ResponsesStructuredModel
from app.standards.evidence import EvidenceRegistry

PHASE2_CONFIGURATION_ID = "m3-live-phase2-gpt-5.5-frozen-graph-v2"
PHASE2_RESULTS_ROOT = REPOSITORY_ROOT / "results" / "live"
PHASE2_PAPER_ROOT = REPOSITORY_ROOT / "paper" / "tables" / "live"
PHASE2_SCHEDULED_OUTCOMES = PHASE2_CASE_COUNT * len(LIVE_SYSTEMS) * PHASE2_REPETITIONS
PHASE2_RUN_ID_PATTERN = re.compile(r"^m3-live-phase2-[0-9]{8}T[0-9]{12}Z$")


class LivePhase2Error(RuntimeError):
    """A frozen held-out run failed its integrity boundary."""


@dataclass(frozen=True)
class RepetitionOutcome:
    repetition_index: int
    value: LiveOutcome


def _guard_held_out_case(case: BenchmarkCase, *, location: str) -> None:
    if case.split != "test":
        raise LivePhase2Error(f"Phase 2 rejected non-held-out membership at {location}")


def _phase2_model(settings: Settings, count_tokens: Any) -> ResponsesStructuredModel:
    return ResponsesStructuredModel(
        base_url=cast(str, settings.llm_base_url),
        api_key=cast(SecretStr, settings.llm_api_key).get_secret_value(),
        model=cast(str, settings.llm_model),
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=LIVE_REASONING_EFFORT,
        max_output_tokens=PHASE2_MAX_OUTPUT_TOKENS,
        count_final_tokens=lambda text: len(count_tokens(text)),
        final_answer_token_limit=LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
        input_character_limit=LIVE_INPUT_CHARACTER_LIMIT,
    )


def _run_id() -> str:
    return f"m3-live-phase2-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def _declared_benchmark_digest() -> str:
    path = REPOSITORY_ROOT / "data/benchmark/frozen/benchmark-v1.0.0.sha256"
    return path.read_text(encoding="utf-8").strip().split()[0]


def _static_manifest(*, run_id: str, gate: HeldOutApprovalGate) -> dict[str, Any]:
    material = configuration_material(max_output_tokens=PHASE2_MAX_OUTPUT_TOKENS)
    prompt_digests = template_digests(material)
    return {
        "manifest_version": "1.0.0",
        "run_id": run_id,
        "configuration_id": PHASE2_CONFIGURATION_ID,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_type": "live_model_run",
        "phase": "phase2-held-out-test",
        "state": "prepared",
        "stop_reason": "awaiting_held_out_loading",
        "empirical_model_run": True,
        "eligible_for_performance_claims": False,
        "eligibility_policy": "true only after a complete held-out integrity audit",
        "current_fda_operational_availability": "not_operational",
        "expert_validated": False,
        "author_approval": {
            "author_id": "author-01",
            "phase1_complete_approved": True,
            "held_out_authorized": True,
            "prompt_freeze_authorized": True,
            "max_output_tokens": PHASE2_MAX_OUTPUT_TOKENS,
            "final_structured_answer_token_limit": LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
        },
        "frozen_prompt_digest": gate.frozen_prompt_digest,
        "frozen_configuration_digest": gate.frozen_configuration_digest,
        "freeze_component_digests": phase2_freeze_components(material),
        "prompt_template_digests": prompt_digests,
        "prompt_template_versions": {
            "direct_decision": DIRECT_DECISION_PROMPT_VERSION,
            "semantic_inspection": SEMANTIC_INSPECTION_PROMPT_VERSION,
        },
        "configuration_material": material,
        "model_configuration": {
            "model": "gpt-5.5",
            "reasoning_effort": LIVE_REASONING_EFFORT,
            "max_output_tokens": PHASE2_MAX_OUTPUT_TOKENS,
            "final_structured_answer_token_limit": LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
            "input_character_limit": LIVE_INPUT_CHARACTER_LIMIT,
            "temperature_handling": TEMPERATURE_HANDLING,
            "retry_limit": LIVE_RETRY_LIMIT,
        },
        "graph_contract_disclosure": material["graph_contract"],
        "benchmark": {
            "sha256": _declared_benchmark_digest(),
            "bytes_labels_families_and_splits_immutable": True,
            "held_out_loaded_at_manifest_creation": False,
        },
        "repetition_design": {
            "live_systems": list(LIVE_SYSTEMS),
            "held_out_cases_per_system": PHASE2_CASE_COUNT,
            "repetitions": PHASE2_REPETITIONS,
            "scheduled_live_outcomes": PHASE2_SCHEDULED_OUTCOMES,
            "fresh_responses_each_repetition": True,
            "response_cache_substitution": False,
            "majority_vote": False,
            "pooled_prediction": False,
            "reporting": "per repetition plus min-max ranges",
        },
        "failure_stop_policy": (
            "transport/provider-API failures may retry twice; schema, citation, graph, "
            "persistence, synthesis, frozen-digest mismatch, new failure class, truncation, "
            "or audit failure stops the phase without a configuration change"
        ),
        "scoring_policy": {
            "reference_join": "after predictions exist within each repetition",
            "invalid_output": "excluded from decision metrics and reported separately",
            "outside_represented_class": "primary exact-match error; sensitivity exclusion only",
            "intervals": "exploratory only; no independence or significance claims",
        },
        "pricing": {
            "currency": "USD",
            "per_million_tokens": PRICING_PER_MILLION,
            "source": "https://developers.openai.com/api/docs/models/gpt-5.5",
            "unknown_usage_policy": "unknown, never zero",
        },
    }


def prepare_phase2_run() -> Path:
    gate = load_phase2_approval_gate()
    gate.guard()
    run_id = _run_id()
    result_dir = PHASE2_RESULTS_ROOT / run_id
    paper_dir = PHASE2_PAPER_ROOT / run_id
    manifest = _static_manifest(run_id=run_id, gate=gate)
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _atomic_write(result_dir / "manifest.pre-run.json", rendered)
    _atomic_write(paper_dir / "manifest.pre-run.json", rendered)
    return result_dir


def _validate_run_id(run_id: str) -> None:
    if not PHASE2_RUN_ID_PATTERN.fullmatch(run_id):
        raise LivePhase2Error("Phase 2 run ID is not an allowed generated identifier")


def _load_prepared_manifest(run_id: str, gate: HeldOutApprovalGate) -> dict[str, Any]:
    _validate_run_id(run_id)
    path = PHASE2_RESULTS_ROOT / run_id / "manifest.pre-run.json"
    if not path.is_file():
        raise LivePhase2Error("Prepared Phase 2 manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("run_id") != run_id
        or manifest.get("state") != "prepared"
        or manifest.get("frozen_prompt_digest") != gate.frozen_prompt_digest
        or manifest.get("frozen_configuration_digest") != gate.frozen_configuration_digest
        or manifest.get("benchmark", {}).get("held_out_loaded_at_manifest_creation") is not False
    ):
        raise LivePhase2Error("Prepared Phase 2 manifest failed integrity validation")
    return manifest


def _validate_repetition_outcomes(outcomes: tuple[RepetitionOutcome, ...]) -> None:
    keys = [
        (item.repetition_index, item.value.system, item.value.case_id) for item in outcomes
    ]
    if len(keys) != len(set(keys)):
        raise LivePhase2Error("Duplicate Phase 2 repetition/system/case outcome")
    for repetition in range(1, PHASE2_REPETITIONS + 1):
        values = tuple(item.value for item in outcomes if item.repetition_index == repetition)
        _validate_outcomes_for_write(values)


def _score_repetitions(
    bundle: Phase2Bundle, outcomes: tuple[RepetitionOutcome, ...]
) -> tuple[tuple[dict[str, Any], ...], tuple[CaseEvaluation, ...]]:
    reports: list[dict[str, Any]] = []
    rows: list[CaseEvaluation] = []
    regulatory_ids = frozenset(item.id for item in EvidenceRegistry().load())
    for repetition in range(1, PHASE2_REPETITIONS + 1):
        repeated = tuple(item.value for item in outcomes if item.repetition_index == repetition)
        for system in LIVE_SYSTEMS:
            system_outcomes = tuple(item for item in repeated if item.system == system)
            if len(system_outcomes) != PHASE2_CASE_COUNT:
                continue
            predictions = tuple(
                cast(SystemPrediction, item.prediction)
                for item in system_outcomes if item.prediction is not None
            )
            if not predictions:
                continue
            traces = tuple(item.retrieval for item in system_outcomes if item.retrieval is not None)
            valid_ids = {prediction.case_id for prediction in predictions}
            cases = tuple(case for case in bundle.cases if case.case_id in valid_ids)
            report, evaluations = score_system(
                cases=cases,
                predictions=predictions,
                retrieval_traces=traces,
                scope="held-out-test",
                seed=LIVE_SEED + repetition,
                regulatory_evidence_ids=regulatory_ids,
            )
            report = report.model_copy(update={
                "result_status": "live model output",
                "interval_interpretation": (
                    "exploratory only; no independence or significance claim"
                ),
            })
            reports.append({
                "repetition_index": repetition,
                "system": system,
                "report": report.model_dump(mode="json"),
            })
            rows.extend(evaluations)
    return tuple(reports), tuple(rows)


def _metric_value(report: dict[str, Any], key: str) -> float | None:
    value: Any = report["report"]
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return float(value) if isinstance(value, int | float) else None


def _metric_ranges(reports: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    fields = (
        "accuracy", "macro_f1", "balanced_accuracy",
        "unsafe_false_negative_rate.rate", "review_bypass_rate.rate",
        "vocabulary_diagnostic.outside_represented_rate", "evidence_citation_accuracy",
        "repair_action_accuracy", "abstention_accuracy", "heading_mapping_accuracy",
    )
    output: dict[str, Any] = {}
    for system in LIVE_SYSTEMS:
        system_reports = tuple(item for item in reports if item["system"] == system)
        output[system] = {}
        for field in fields:
            values = [
                value for item in system_reports
                if (value := _metric_value(item, field)) is not None
            ]
            output[system][field] = (
                {"min": min(values), "max": max(values)} if values else None
            )
    return output


def _invalid_diagnostics(outcomes: tuple[RepetitionOutcome, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for repetition in range(1, PHASE2_REPETITIONS + 1):
        result[str(repetition)] = {}
        for system in LIVE_SYSTEMS:
            values = [
                item.value for item in outcomes
                if item.repetition_index == repetition and item.value.system == system
            ]
            invalid = sum(item.outcome == "invalid_output" for item in values)
            result[str(repetition)][system] = {
                "completed": len(values),
                "scheduled": PHASE2_CASE_COUNT,
                "invalid_outputs": invalid,
                "failure_rate": invalid / PHASE2_CASE_COUNT,
                "over_10_percent_uninterpretable": invalid >= 2,
            }
    return result


def _usage(outcomes: tuple[RepetitionOutcome, ...]) -> dict[str, Any]:
    per_repetition = {
        str(repetition): _usage_summary(tuple(
            item.value for item in outcomes if item.repetition_index == repetition
        ))
        for repetition in range(1, PHASE2_REPETITIONS + 1)
    }
    overall = _usage_summary(tuple(item.value for item in outcomes))
    costs = [
        _cost(item.value.attempts) for item in outcomes
        if _cost(item.value.attempts) is not None
    ]
    return {
        "per_repetition": per_repetition,
        "overall": overall,
        "total_cost_usd": sum(cast(float, value) for value in costs),
        "unknown_cost_outcomes": sum(_cost(item.value.attempts) is None for item in outcomes),
    }


def _outcomes_jsonl(outcomes: tuple[RepetitionOutcome, ...]) -> str:
    return "".join(
        json.dumps({
            "repetition_index": item.repetition_index,
            "system": item.value.system,
            "case_id": item.value.case_id,
            "split": item.value.split,
            "outcome": item.value.outcome,
            "prediction": (
                item.value.prediction.model_dump(mode="json")
                if item.value.prediction is not None else None
            ),
            "failure": item.value.failure,
            "retrieval": (
                item.value.retrieval.model_dump(mode="json")
                if item.value.retrieval is not None else None
            ),
            "attempts": [attempt.to_json() for attempt in item.value.attempts],
            "deviation_log": item.value.deviation_log,
        }, sort_keys=True, ensure_ascii=False) + "\n"
        for item in outcomes
    )


def _per_case_csv(outcomes: tuple[RepetitionOutcome, ...]) -> str:
    output = io.StringIO(newline="")
    fields = (
        "repetition_index", "system", "case_id", "fixture_family", "outcome",
        "decision", "action", "human_review_required", "attempts", "failure", "cost_usd",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    family_by_case: dict[str, str] = {}
    if PHASE2_BUNDLE.is_file():
        family_by_case = {case.case_id: case.fixture_family for case in load_phase2_bundle().cases}
    for item in outcomes:
        prediction = item.value.prediction
        writer.writerow({
            "repetition_index": item.repetition_index,
            "system": item.value.system,
            "case_id": item.value.case_id,
            "fixture_family": family_by_case.get(item.value.case_id),
            "outcome": item.value.outcome,
            "decision": prediction.decision.value if prediction else None,
            "action": prediction.action if prediction else None,
            "human_review_required": prediction.human_review_required if prediction else None,
            "attempts": len(item.value.attempts),
            "failure": item.value.failure,
            "cost_usd": _cost(item.value.attempts),
        })
    return output.getvalue()


def _summary(manifest: dict[str, Any]) -> str:
    rows = [
        "# M3 Phase 2 held-out live evaluation\n",
        f"Run: `{manifest['run_id']}`. State: `{manifest['state']}`. "
        f"Stop reason: `{manifest['stop_reason']}`.\n",
        f"Recorded {manifest['progress']['completed_outcomes']}/"
        f"{manifest['progress']['scheduled_outcomes']} scheduled live outcomes. "
        "No voting or pooled predictions.\n",
        "FDA availability: `not_operational`; `expert_validated: false`. "
        "Eligible for performance claims: "
        f"`{str(manifest['eligible_for_performance_claims']).lower()}`.\n",
        "| System | Repetition | Valid n | Accuracy | Macro-F1 | Unsafe misses / eligible | "
        "Review bypass / HUMAN | Outside represented classes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in manifest.get("per_repetition_reports", []):
        report = item["report"]
        unsafe = report["unsafe_false_negative_rate"]
        review = report["review_bypass_rate"]
        vocab = report["vocabulary_diagnostic"]
        valid = sum(value["support"] for value in report["per_class"].values())
        rows.append(
            f"| {item['system']} | {item['repetition_index']} | {valid} | "
            f"{report['accuracy']:.3f} | {report['macro_f1']:.3f} | "
            f"{unsafe['numerator']}/{unsafe['denominator']} | "
            f"{review['numerator']}/{review['denominator']} | "
            f"{vocab['outside_represented_count']}/{vocab['valid_prediction_count']} |"
        )
        if vocab.get("safety_caveat"):
            rows.append(f"\n{item['system']} repetition {item['repetition_index']}: "
                        f"{vocab['safety_caveat']}\n")
    if b2_report := manifest.get("b2_report"):
        unsafe = b2_report["unsafe_false_negative_rate"]
        review = b2_report["review_bypass_rate"]
        vocab = b2_report["vocabulary_diagnostic"]
        valid = sum(value["support"] for value in b2_report["per_class"].values())
        rows.append(
            f"| B2 | once | {valid} | {b2_report['accuracy']:.3f} | "
            f"{b2_report['macro_f1']:.3f} | {unsafe['numerator']}/{unsafe['denominator']} | "
            f"{review['numerator']}/{review['denominator']} | "
            f"{vocab['outside_represented_count']}/{vocab['valid_prediction_count']} |"
        )
    rows.extend([
        "\n## Min-max ranges across the three separate repetitions\n",
        "```json",
        json.dumps(manifest.get("metric_ranges", {}), indent=2, sort_keys=True),
        "```",
        "\n## Family-clustered sensitivity\n",
        "Intervals below are exploratory only. No independence or significance claim is made.",
    ])
    for item in manifest.get("per_repetition_reports", []):
        report = item["report"]
        rows.append(
            f"\n- {item['system']} repetition {item['repetition_index']}: "
            f"families_with_unsafe_misses={report['families_with_unsafe_misses']}/"
            f"{report['action_required_family_count']} action-required families; "
            f"cluster_bootstrap_unsafe_fnr_95={report['cluster_bootstrap_unsafe_fnr_95']}; "
            f"family_counts={json.dumps(report['family_sensitivity'], sort_keys=True)}"
        )
    rows.extend([
        "\n## Usage and cost\n",
        "```json",
        json.dumps(manifest.get("usage", {}), indent=2, sort_keys=True),
        "```",
        "\nB2 was recomputed once from the production parser, graph, and deterministic rules "
        "with semantic capability omitted; it made no model calls.",
    ])
    return "\n".join(rows) + "\n"


def _write_artifacts(
    *,
    run_id: str,
    prepared: dict[str, Any],
    bundle: Phase2Bundle,
    outcomes: tuple[RepetitionOutcome, ...],
    b2: Phase2B2Rescore,
    state: Literal["running", "failed", "completed"],
    stop_reason: str,
) -> Path:
    _validate_repetition_outcomes(outcomes)
    reports, evaluations = _score_repetitions(bundle, outcomes)
    complete = len(outcomes) == PHASE2_SCHEDULED_OUTCOMES and all(
        item.value.outcome == "valid_prediction" for item in outcomes
    )
    if state == "completed" and not complete:
        raise LivePhase2Error("Completed Phase 2 state requires all valid scheduled outcomes")
    if state == "running" and complete:
        raise LivePhase2Error("Running Phase 2 artifact cannot contain a complete schedule")
    predictions = _outcomes_jsonl(outcomes)
    metrics = {
        "run_type": "live_model_run",
        "phase": "phase2-held-out-test",
        "empirical_model_run": True,
        "eligible_for_performance_claims": state == "completed",
        "current_fda_operational_availability": "not_operational",
        "expert_validated": False,
        "state": state,
        "stop_reason": stop_reason,
        "per_repetition_reports": reports,
        "metric_ranges": _metric_ranges(reports),
        "b2_report": b2.report.model_dump(mode="json"),
        "invalid_output_diagnostics": _invalid_diagnostics(outcomes),
    }
    metrics_text = json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    manifest = dict(prepared)
    manifest.update({
        "state": state,
        "stop_reason": stop_reason,
        "eligible_for_performance_claims": state == "completed",
        "integrity_audit": {
            "passed": state == "completed" and complete,
            "new_failure_class": None if state == "completed" else stop_reason,
            "truncation_count": sum(
                attempt.ceiling_hit for item in outcomes for attempt in item.value.attempts
            ),
        },
        "progress": {
            "completed_outcomes": len(outcomes),
            "scheduled_outcomes": PHASE2_SCHEDULED_OUTCOMES,
            "terminal_audit_complete": state != "running",
            "completed_by_repetition_and_system": {
                str(repetition): {
                    system: sum(
                        item.repetition_index == repetition and item.value.system == system
                        for item in outcomes
                    ) for system in LIVE_SYSTEMS
                } for repetition in range(1, PHASE2_REPETITIONS + 1)
            },
        },
        "held_out_bundle": {
            "path": PHASE2_BUNDLE.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": phase2_bundle_sha256(),
            "case_count": len(bundle.cases),
            "fixture_family_count": len({case.fixture_family for case in bundle.cases}),
        },
        "per_repetition_reports": reports,
        "metric_ranges": _metric_ranges(reports),
        "b2_report": b2.report.model_dump(mode="json"),
        "invalid_output_diagnostics": _invalid_diagnostics(outcomes),
        "usage": _usage(outcomes),
        "retry_log": [
            {
                "repetition_index": item.repetition_index,
                "system": item.value.system,
                "case_id": item.value.case_id,
                "deviations": item.value.deviation_log,
            }
            for item in outcomes if item.value.deviation_log
        ],
        "b2_rescore": {
            "result_status": "genuine deterministic experimental output",
            "model_calls": 0,
            "repetitions": 1,
            "sha256": content_digest(b2.artifact()),
            "artifact": "b2-held-out-rescore.json",
        },
        "artifact_digests": {
            "predictions_sha256": _digest_bytes(predictions.encode("utf-8")),
            "metrics_sha256": _digest_bytes(metrics_text.encode("utf-8")),
        },
    })
    result_dir = PHASE2_RESULTS_ROOT / run_id
    paper_dir = PHASE2_PAPER_ROOT / run_id
    suffix = ".partial" if state == "running" else ""
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _atomic_write(result_dir / f"manifest{suffix}.json", manifest_text)
    _atomic_write(result_dir / f"predictions{suffix}.jsonl", predictions)
    _atomic_write(result_dir / f"metrics{suffix}.json", metrics_text)
    _atomic_write(result_dir / f"per-case{suffix}.csv", _per_case_csv(outcomes))
    _atomic_write(result_dir / f"summary{suffix}.md", _summary(manifest))
    _atomic_write(result_dir / "b2-held-out-rescore.json", json.dumps(
        b2.artifact(), indent=2, sort_keys=True
    ) + "\n")
    _atomic_write(result_dir / f"attempts{suffix}.jsonl", "".join(
        json.dumps({
            "repetition_index": item.repetition_index,
            "system": item.value.system,
            "case_id": item.value.case_id,
            "attempt": attempt.to_json(),
        }, sort_keys=True) + "\n"
        for item in outcomes for attempt in item.value.attempts
    ))
    _atomic_write(result_dir / f"retrieval{suffix}.jsonl", "".join(
        json.dumps({
            "repetition_index": item.repetition_index,
            "trace": item.value.retrieval.model_dump(mode="json"),
        }, sort_keys=True) + "\n"
        for item in outcomes if item.value.retrieval is not None
    ))
    _atomic_write(paper_dir / f"m3-live-phase2-held-out-summary{suffix}.md", _summary(manifest))
    _atomic_write(paper_dir / f"m3-live-phase2-held-out-metrics{suffix}.json", metrics_text)
    _atomic_write(
        paper_dir / f"m3-live-phase2-held-out-per-case{suffix}.csv",
        _per_case_csv(outcomes),
    )
    if state != "running":
        audit = {
            "run_id": run_id,
            "state": state,
            "stop_reason": stop_reason,
            "integrity_audit_passed": manifest["integrity_audit"]["passed"],
            "completed_outcomes": len(outcomes),
            "scheduled_outcomes": PHASE2_SCHEDULED_OUTCOMES,
            "frozen_prompt_digest": manifest["frozen_prompt_digest"],
            "frozen_configuration_digest": manifest["frozen_configuration_digest"],
            "invalid_output_diagnostics": manifest["invalid_output_diagnostics"],
            "truncation_count": manifest["integrity_audit"]["truncation_count"],
            "metric_ranges": manifest["metric_ranges"],
            "usage": manifest["usage"],
            "current_fda_operational_availability": "not_operational",
            "expert_validated": False,
        }
        audit_text = json.dumps(audit, indent=2, sort_keys=True) + "\n"
        _atomic_write(result_dir / "completion-audit.json", audit_text)
        _atomic_write(paper_dir / "completion-audit.json", audit_text)
    return result_dir


async def execute_phase2(run_id: str) -> Path:
    gate = load_phase2_approval_gate()
    prepared = _load_prepared_manifest(run_id, gate)
    bundle = gate.before_loading(lambda: write_phase2_bundle())
    bundle = load_phase2_bundle()
    gate.guard()
    b2 = await rescore_phase2_b2(
        bundle, seed=LIVE_SEED, frozen_configuration_digest=gate.frozen_configuration_digest
    )
    settings = _settings()
    tokenizer_name, counter = _token_counter(cast(str, settings.llm_model))
    prepared["model_configuration"]["tokenizer"] = tokenizer_name
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    retriever = BM25Retriever(evidence)
    by_input = {item.case_id: item for item in bundle.case_inputs}
    ordered_cases = tuple(
        next(case for case in bundle.cases if case.case_id == case_id)
        for case_id in sorted(by_input)
    )
    outcomes: list[RepetitionOutcome] = []
    _write_artifacts(
        run_id=run_id, prepared=prepared, bundle=bundle, outcomes=(), b2=b2,
        state="running", stop_reason="run_in_progress",
    )
    try:
        for repetition in range(1, PHASE2_REPETITIONS + 1):
            gate.before_repetition(lambda: None)
            model = _phase2_model(settings, counter)
            for system in LIVE_SYSTEMS:
                for case in ordered_cases:
                    gate.before_dispatch(lambda: None)
                    _guard_held_out_case(case, location="scheduled dispatch")
                    if system in {"B0", "B1"}:
                        outcome = await _run_direct(
                            system=cast(Literal["B0", "B1"], system),
                            case=case,
                            bundle=cast(Any, bundle),
                            model=model,
                            evidence=evidence,
                            retriever=retriever,
                            first_authorized_request=False,
                            guard_case=_guard_held_out_case,
                            phase_name="Phase 2",
                            dispatch_guard=gate.guard,
                        )
                    else:
                        outcome = await _run_regbridge(
                            case=case,
                            bundle=cast(Any, bundle),
                            model=model,
                            first_authorized_request=False,
                            guard_case=_guard_held_out_case,
                            dispatch_guard=gate.guard,
                        )
                    outcomes.append(RepetitionOutcome(repetition, outcome))
                    if any(attempt.ceiling_hit for attempt in outcome.attempts):
                        return _write_artifacts(
                            run_id=run_id, prepared=prepared, bundle=bundle,
                            outcomes=tuple(outcomes), b2=b2, state="failed",
                            stop_reason="max_output_tokens_truncation",
                        )
                    if outcome.outcome == "invalid_output":
                        return _write_artifacts(
                            run_id=run_id, prepared=prepared, bundle=bundle,
                            outcomes=tuple(outcomes), b2=b2, state="failed",
                            stop_reason=outcome.failure or "new_failure_class",
                        )
                    if len(outcomes) < PHASE2_SCHEDULED_OUTCOMES:
                        _write_artifacts(
                            run_id=run_id, prepared=prepared, bundle=bundle,
                            outcomes=tuple(outcomes), b2=b2, state="running",
                            stop_reason="run_in_progress",
                        )
                    print(
                        f"Phase 2 repetition {repetition}: {len(outcomes)}/"
                        f"{PHASE2_SCHEDULED_OUTCOMES} outcomes recorded ({system}).",
                        flush=True,
                    )
    except HeldOutConfigurationMismatch as error:
        return _write_artifacts(
            run_id=run_id, prepared=prepared, bundle=bundle, outcomes=tuple(outcomes),
            b2=b2, state="failed", stop_reason=f"frozen_configuration_mismatch:{error}",
        )
    return _write_artifacts(
        run_id=run_id, prepared=prepared, bundle=bundle, outcomes=tuple(outcomes),
        b2=b2, state="completed", stop_reason="completed_without_failure",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or execute frozen M3 live Phase 2.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute", metavar="RUN_ID")
    args = parser.parse_args()
    if args.prepare:
        path = prepare_phase2_run()
        print(path.name)
        print(f"Prepared manifest: {(path / 'manifest.pre-run.json').relative_to(REPOSITORY_ROOT)}")
        return
    run_id = cast(str, args.execute)
    try:
        path = asyncio.run(execute_phase2(run_id))
    except Exception as error:
        _validate_run_id(run_id)
        path = PHASE2_RESULTS_ROOT / run_id
        failure = {
            "run_id": run_id,
            "state": "failed",
            "stop_reason": f"new_failure_class_or_audit_failure:{type(error).__name__}",
            "retryable": False,
            "prompts_or_configuration_changed": False,
            "current_fda_operational_availability": "not_operational",
            "expert_validated": False,
        }
        _atomic_write(
            path / "fatal-audit-failure.json",
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
        )
        print(f"State: failed; stop_reason={failure['stop_reason']}")
        raise SystemExit(1) from error
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    print(f"Phase 2 artifacts written to {path.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"State: {manifest['state']}; stop_reason={manifest['stop_reason']}")
    if manifest["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
