import argparse
import asyncio
import csv
import hashlib
import io
import json
import math
import os
import statistics
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import SecretStr

from app.analyzer.service import AnalysisService
from app.baselines.direct import (
    DIRECT_INPUT_CHARACTER_LIMIT,
    DIRECT_OUTPUT_TOKEN_LIMIT,
    DIRECT_TEMPERATURE,
    prepare_case,
    serialize_direct_request,
)
from app.baselines.prompts import DIRECT_DECISION_PROMPT_VERSION
from app.baselines.retrieval import BM25Retriever
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import Decision, LlmMode
from app.evaluation.metrics import score_system
from app.evaluation.models import (
    BenchmarkCase,
    CaseEvaluation,
    DirectDecisionOutput,
    MetricsReport,
    RetrievalTrace,
    SystemName,
    SystemPrediction,
)
from app.evaluation.phase1_bundle import (
    PHASE1_ALLOWED_SPLITS,
    PHASE1_BUNDLE,
    Phase1Bundle,
    load_phase1_bundle,
    phase1_bundle_sha256,
    write_phase1_bundle,
)
from app.llm.responses import LiveModelInvalidOutput, ResponsesAttempt, ResponsesStructuredModel
from app.parsers.ectd322 import parse_directory
from app.standards.evidence import EvidenceRegistry

LIVE_SYSTEMS: tuple[SystemName, ...] = ("B0", "B1", "RegBridge")
LIVE_CONFIGURATION_ID = "m3-live-phase1-gpt-5.5-train-dev-v1"
LIVE_RUN_TYPE = "live_model_run"
LIVE_REASONING_EFFORT = "medium"
LIVE_PILOT_OUTPUT_CEILING = 25_000
LIVE_FINAL_SCHEMA_TOKEN_LIMIT = DIRECT_OUTPUT_TOKEN_LIMIT
LIVE_INPUT_CHARACTER_LIMIT = DIRECT_INPUT_CHARACTER_LIMIT
LIVE_RETRY_LIMIT = 2
LIVE_SEED = 20270829
LIVE_RESULTS_ROOT = REPOSITORY_ROOT / "results" / "live"
LIVE_PAPER_ROOT = REPOSITORY_ROOT / "paper" / "tables" / "live"
PRICING_PER_MILLION = {"input": 5.00, "cached_input": 0.50, "output": 30.00}


class LivePhase1Error(RuntimeError):
    """Raised when Phase 1 cannot proceed without author direction."""


@dataclass(frozen=True)
class LiveOutcome:
    system: SystemName
    case_id: str
    split: str
    outcome: Literal["valid_prediction", "invalid_output"]
    prediction: SystemPrediction | None
    retrieval: RetrievalTrace | None
    attempts: tuple[ResponsesAttempt, ...]
    deviation_log: tuple[dict[str, Any], ...]
    failure: str | None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _token_counter(model: str) -> tuple[str, Any]:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError as error:
        raise LivePhase1Error(
            "tiktoken is required for exact final-answer token validation before live calls"
        ) from error
    try:
        encoding = tiktoken.encoding_for_model(model)
        tokenizer_name = f"tiktoken:{encoding.name}:encoding_for_model:{model}"
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
        tokenizer_name = "tiktoken:o200k_base:fallback_for_gpt_5_family"
    return tokenizer_name, encoding.encode


def _settings() -> Settings:
    settings = Settings(llm_mode=LlmMode.LIVE)
    if settings.llm_model != "gpt-5.5":
        raise LivePhase1Error("Phase 1 is approved only for LLM_MODEL=gpt-5.5")
    return settings


def _case_map(bundle: Phase1Bundle) -> dict[str, BenchmarkCase]:
    _guard_phase1_cases(bundle.cases, location="case map")
    return {case.case_id: case for case in bundle.cases}


def _guard_phase1_cases(cases: tuple[BenchmarkCase, ...], *, location: str) -> None:
    if any(case.split not in PHASE1_ALLOWED_SPLITS for case in cases):
        raise LivePhase1Error(f"Phase 1 guard rejected disallowed split at {location}")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise LivePhase1Error(f"Phase 1 guard rejected duplicate case identifiers at {location}")


def _guard_case(case: BenchmarkCase, *, location: str) -> None:
    if case.split not in PHASE1_ALLOWED_SPLITS:
        raise LivePhase1Error(f"Phase 1 guard rejected disallowed split at {location}")


def _model(settings: Settings, count_tokens: Any) -> ResponsesStructuredModel:
    return ResponsesStructuredModel(
        base_url=cast(str, settings.llm_base_url),
        api_key=cast(SecretStr, settings.llm_api_key).get_secret_value(),
        model=cast(str, settings.llm_model),
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=LIVE_REASONING_EFFORT,
        max_output_tokens=LIVE_PILOT_OUTPUT_CEILING,
        temperature=DIRECT_TEMPERATURE,
        count_final_tokens=lambda text: len(count_tokens(text)),
        final_answer_token_limit=LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
        input_character_limit=LIVE_INPUT_CHARACTER_LIMIT,
    )


async def _run_direct(
    *,
    system: Literal["B0", "B1"],
    case: BenchmarkCase,
    bundle: Phase1Bundle,
    model: ResponsesStructuredModel,
    evidence: tuple[Any, ...],
    retriever: BM25Retriever,
    first_authorized_request: bool,
) -> LiveOutcome:
    _guard_case(case, location=f"{system} input preparation")
    case_input = next(item for item in bundle.case_inputs if item.case_id == case.case_id)
    prepared = prepare_case(case_input)
    retrieval: RetrievalTrace | None = None
    selected = evidence
    if system == "B1":
        retrieval = retriever.retrieve(case_id=case.case_id, query=prepared.serialized)
        by_id = {item.id: item for item in evidence}
        selected = tuple(by_id[item.evidence_id] for item in retrieval.hits)
    serialized = serialize_direct_request(prepared, selected)
    if len(serialized) > LIVE_INPUT_CHARACTER_LIMIT:
        raise LivePhase1Error("Phase 1 direct request exceeded the input character limit")
    attempts, output, failure = await _retry_live_call(
        model=model,
        call=lambda: model.complete_text(
            input_text=serialized,
            output_type=DirectDecisionOutput,
            prompt_template_version=DIRECT_DECISION_PROMPT_VERSION,
        ),
        first_authorized_request=first_authorized_request,
    )
    deviations = _deviations(attempts)
    if output is None:
        return LiveOutcome(
            system=system,
            case_id=case.case_id,
            split=case.split,
            outcome="invalid_output",
            prediction=None,
            retrieval=retrieval,
            attempts=attempts,
            deviation_log=deviations,
            failure=failure,
        )
    prediction = SystemPrediction(
        system=system,
        case_id=case.case_id,
        decision=output.decision,
        severity=output.severity,
        action=output.action,
        human_review_required=output.human_review_required,
        unconditional_reuse=(
            output.decision == Decision.REUSE_AS_LEGACY_REFERENCE
            and output.action == "NO_MATERIAL_REPAIR"
            and not output.human_review_required
        ),
        rationale=output.rationale,
        evidence_ids=output.evidence_ids,
        rule_ids=(),
        confidence=output.confidence,
        prediction_source="live_direct_model",
        empirical_model_observation=True,
        latency_ms=sum(item.latency_ms for item in attempts),
        requests=len(attempts),
        input_tokens=sum(item.input_tokens or 0 for item in attempts),
        output_tokens=sum(item.total_output_tokens or 0 for item in attempts),
        cost_usd=_cost(attempts),
    )
    return LiveOutcome(
        system=system,
        case_id=case.case_id,
        split=case.split,
        outcome="valid_prediction",
        prediction=prediction,
        retrieval=retrieval,
        attempts=attempts,
        deviation_log=deviations,
        failure=None,
    )


async def _run_regbridge(
    *,
    case: BenchmarkCase,
    bundle: Phase1Bundle,
    model: ResponsesStructuredModel,
    first_authorized_request: bool,
) -> LiveOutcome:
    _guard_case(case, location="RegBridge input preparation")
    metadata = {item.fixture_id: item for item in bundle.fixture_metadata}
    fixture = metadata[case.fixture_id]
    fixture_path = (REPOSITORY_ROOT / "data" / "demo-cases" / fixture.relative_path).resolve()
    inventory = parse_directory(
        fixture_path,
        fixture_id=fixture.fixture_id,
        author_verified_relevant_hyperlink_ids=fixture.author_verified_relevant_hyperlink_ids,
    )
    service = AnalysisService(
        settings=Settings(
            llm_mode=LlmMode.LIVE,
            llm_model=cast(str, model.model),
            llm_base_url=model.base_url,
            llm_api_key=SecretStr("redacted"),
        ),
        model=model,
    )
    attempts, result, failure = await _retry_live_call(
        model=model,
        call=lambda: service.analyze_async(inventory, case.selected_leaf_id, case.target_context),
        first_authorized_request=first_authorized_request,
    )
    deviations = _deviations(attempts)
    if result is None or (result.model_run.status == "failed" and attempts):
        return LiveOutcome(
            system="RegBridge",
            case_id=case.case_id,
            split=case.split,
            outcome="invalid_output",
            prediction=None,
            retrieval=None,
            attempts=attempts,
            deviation_log=deviations,
            failure=failure or result.model_run.validation_error if result else failure,
        )
    prediction = SystemPrediction(
        system="RegBridge",
        case_id=case.case_id,
        decision=result.decision,
        severity=result.severity,
        action=result.repair.type,
        human_review_required=result.human_approval_required,
        unconditional_reuse=(
            result.decision == Decision.REUSE_AS_LEGACY_REFERENCE
            and result.repair.type == "NO_MATERIAL_REPAIR"
            and not result.human_approval_required
        ),
        rationale=result.rationale,
        evidence_ids=tuple(item.id for item in result.evidence),
        rule_ids=result.triggered_rule_ids,
        confidence=result.confidence,
        prediction_source="live_hybrid_model",
        empirical_model_observation=True,
        latency_ms=sum(item.latency_ms for item in attempts),
        requests=len(attempts),
        input_tokens=sum(item.input_tokens or 0 for item in attempts),
        output_tokens=sum(item.total_output_tokens or 0 for item in attempts),
        cost_usd=_cost(attempts),
    )
    return LiveOutcome(
        system="RegBridge",
        case_id=case.case_id,
        split=case.split,
        outcome="valid_prediction",
        prediction=prediction,
        retrieval=None,
        attempts=attempts,
        deviation_log=deviations,
        failure=None,
    )


async def _retry_live_call(
    *,
    model: ResponsesStructuredModel,
    call: Any,
    first_authorized_request: bool,
) -> tuple[tuple[ResponsesAttempt, ...], Any | None, str | None]:
    attempts: list[ResponsesAttempt] = []
    failure: str | None = None
    for retry_index in range(LIVE_RETRY_LIMIT + 1):
        try:
            completion = await call()
            attempts.extend(
                attempt.__class__(**{**attempt.to_json(), "attempt_index": len(attempts) + 1})
                for attempt in model.last_attempts
            )
            _record_temperature_preflight(attempts[-1], enabled=first_authorized_request)
            if any(attempt.ceiling_hit for attempt in attempts):
                failure = "pilot output ceiling was hit"
            return tuple(attempts), getattr(completion, "output", completion), failure
        except (LiveModelInvalidOutput, ValueError) as error:
            attempts.extend(
                attempt.__class__(**{**attempt.to_json(), "attempt_index": len(attempts) + 1})
                for attempt in model.last_attempts
            )
            failure = type(error).__name__
            if attempts:
                _record_temperature_preflight(attempts[-1], enabled=first_authorized_request)
            if retry_index >= LIVE_RETRY_LIMIT:
                return tuple(attempts), None, failure
    return tuple(attempts), None, failure


def _record_temperature_preflight(attempt: ResponsesAttempt, *, enabled: bool) -> None:
    if not enabled:
        return


def _deviations(attempts: tuple[ResponsesAttempt, ...]) -> tuple[dict[str, Any], ...]:
    deviations: list[dict[str, Any]] = []
    for attempt in attempts:
        if attempt.attempt_index > 1:
            deviations.append(
                {
                    "type": "retry",
                    "attempt_index": attempt.attempt_index,
                    "cause": attempt.cause,
                }
            )
        if attempt.ceiling_hit:
            deviations.append(
                {
                    "type": "pilot_output_ceiling_hit",
                    "attempt_index": attempt.attempt_index,
                    "cause": attempt.finish_reason,
                }
            )
        if attempt.temperature_verification != "reported_match":
            deviations.append(
                {
                    "type": "temperature_not_confirmed",
                    "attempt_index": attempt.attempt_index,
                    "status": attempt.temperature_verification,
                }
            )
    return tuple(deviations)


def _cost(attempts: tuple[ResponsesAttempt, ...]) -> float | None:
    total = 0.0
    observed = False
    for attempt in attempts:
        if attempt.input_tokens is None and attempt.total_output_tokens is None:
            continue
        observed = True
        cached = attempt.cached_input_tokens or 0
        input_tokens = max((attempt.input_tokens or 0) - cached, 0)
        output_tokens = attempt.total_output_tokens or 0
        total += (input_tokens / 1_000_000) * PRICING_PER_MILLION["input"]
        total += (cached / 1_000_000) * PRICING_PER_MILLION["cached_input"]
        total += (output_tokens / 1_000_000) * PRICING_PER_MILLION["output"]
    return total if observed else None


def _score_valid(
    *,
    cases: tuple[BenchmarkCase, ...],
    predictions: tuple[SystemPrediction, ...],
    retrieval_traces: tuple[RetrievalTrace, ...],
    scope: str,
    seed: int,
) -> tuple[MetricsReport | None, tuple[CaseEvaluation, ...]]:
    if not predictions:
        return None, ()
    valid_case_ids = {prediction.case_id for prediction in predictions}
    scoped_cases = tuple(case for case in cases if case.case_id in valid_case_ids)
    regulatory_ids = frozenset(item.id for item in EvidenceRegistry().load())
    report, evaluations = score_system(
        cases=scoped_cases,
        predictions=predictions,
        retrieval_traces=retrieval_traces,
        scope=scope,
        seed=seed,
        regulatory_evidence_ids=regulatory_ids,
    )
    return report.model_copy(update={"result_status": "live model output"}), evaluations


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    return float(ordered[max(index, 0)])


def _usage_summary(outcomes: tuple[LiveOutcome, ...]) -> dict[str, Any]:
    by_system: dict[str, list[ResponsesAttempt]] = defaultdict(list)
    for outcome in outcomes:
        by_system[outcome.system].extend(outcome.attempts)
    summary: dict[str, Any] = {}
    for system, attempts in sorted(by_system.items()):
        reasoning = [
            attempt.reasoning_tokens for attempt in attempts if attempt.reasoning_tokens is not None
        ]
        summary[system] = {
            "attempts": len(attempts),
            "reasoning_tokens_min": min(reasoning) if reasoning else None,
            "reasoning_tokens_median": statistics.median(reasoning) if reasoning else None,
            "reasoning_tokens_p95": _percentile(reasoning, 95),
            "reasoning_tokens_max": max(reasoning) if reasoning else None,
            "ceiling_hit_count": sum(attempt.ceiling_hit for attempt in attempts),
            "final_answer_tokens": [attempt.final_answer_tokens for attempt in attempts],
            "total_output_tokens": [attempt.total_output_tokens for attempt in attempts],
            "finish_reasons": [attempt.finish_reason for attempt in attempts],
            "latency_ms_total": sum(attempt.latency_ms for attempt in attempts),
            "cached_input_tokens": sum(attempt.cached_input_tokens or 0 for attempt in attempts),
            "cost_usd": _cost(tuple(attempts)),
        }
    return summary


def _phase2_cap(outcomes: tuple[LiveOutcome, ...]) -> dict[str, Any]:
    attempts = [attempt for outcome in outcomes for attempt in outcome.attempts]
    if any(attempt.ceiling_hit for attempt in attempts):
        return {"status": "withheld", "reason": "pilot output ceiling was hit"}
    observed = [attempt for attempt in attempts if attempt.reasoning_tokens is not None]
    if not observed:
        return {"status": "withheld", "reason": "reasoning token usage was not reported"}
    maximum = max(cast(int, attempt.reasoning_tokens) for attempt in observed)
    contributing = next(attempt for attempt in observed if attempt.reasoning_tokens == maximum)
    raw_cap = 2 * maximum + LIVE_FINAL_SCHEMA_TOKEN_LIMIT
    phase2_cap = max(4000, 500 * math.ceil(raw_cap / 500))
    return {
        "status": "proposed_requires_author_01_approval",
        "maximum_reasoning_tokens": maximum,
        "contributing_attempt": contributing.to_json(),
        "raw_cap": raw_cap,
        "phase2_cap": phase2_cap,
    }


def _outcome_jsonl(outcomes: tuple[LiveOutcome, ...]) -> str:
    lines = []
    for outcome in outcomes:
        lines.append(
            json.dumps(
                {
                    "system": outcome.system,
                    "case_id": outcome.case_id,
                    "split": outcome.split,
                    "outcome": outcome.outcome,
                    "prediction": outcome.prediction.model_dump(mode="json")
                    if outcome.prediction
                    else None,
                    "failure": outcome.failure,
                    "attempts": [attempt.to_json() for attempt in outcome.attempts],
                    "deviation_log": outcome.deviation_log,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )
    return "".join(lines)


def _metrics_json(
    reports: tuple[MetricsReport, ...],
    outcomes: tuple[LiveOutcome, ...],
    cases: tuple[BenchmarkCase, ...],
) -> str:
    invalid_counts: dict[str, dict[str, Any]] = {}
    for system in LIVE_SYSTEMS:
        scheduled = [outcome for outcome in outcomes if outcome.system == system]
        invalid = [outcome for outcome in scheduled if outcome.outcome == "invalid_output"]
        invalid_counts[system] = {
            "invalid_outputs": len(invalid),
            "scheduled_cases": len(scheduled),
            "rate": len(invalid) / len(scheduled) if scheduled else None,
        }
    return (
        json.dumps(
            {
                "run_type": LIVE_RUN_TYPE,
                "empirical_model_run": True,
                "eligible_for_performance_claims": True,
                "current_fda_operational_availability": "not_operational",
                "expert_validated": False,
                "scope": "phase1-development-train-dev-only",
                "scheduled_cases": len(cases) * len(LIVE_SYSTEMS),
                "invalid_output_counts": invalid_counts,
                "reports": [report.model_dump(mode="json") for report in reports],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _per_case_csv(outcomes: tuple[LiveOutcome, ...]) -> str:
    output = io.StringIO(newline="")
    fields = (
        "system",
        "case_id",
        "split",
        "outcome",
        "decision",
        "action",
        "human_review_required",
        "attempts",
        "failure",
        "cost_usd",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for outcome in outcomes:
        prediction = outcome.prediction
        writer.writerow(
            {
                "system": outcome.system,
                "case_id": outcome.case_id,
                "split": outcome.split,
                "outcome": outcome.outcome,
                "decision": prediction.decision.value if prediction else None,
                "action": prediction.action if prediction else None,
                "human_review_required": prediction.human_review_required if prediction else None,
                "attempts": len(outcome.attempts),
                "failure": outcome.failure,
                "cost_usd": _cost(outcome.attempts),
            }
        )
    return output.getvalue()


def _manifest(
    *,
    run_id: str,
    bundle: Phase1Bundle,
    tokenizer_name: str,
    outcomes: tuple[LiveOutcome, ...],
    reports: tuple[MetricsReport, ...],
    predictions_digest: str,
    metrics_digest: str,
) -> dict[str, Any]:
    prompt_material = {
        "direct_prompt": _file_digest(REPOSITORY_ROOT / "backend/app/baselines/prompts.py"),
        "semantic_prompt": _file_digest(REPOSITORY_ROOT / "backend/app/analyzer/prompts.py"),
        "direct_serializer": _file_digest(REPOSITORY_ROOT / "backend/app/baselines/direct.py"),
        "semantic_schema": _file_digest(REPOSITORY_ROOT / "backend/app/llm/models.py"),
    }
    return {
        "manifest_version": "1.0.0",
        "run_id": run_id,
        "configuration_id": LIVE_CONFIGURATION_ID,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_type": LIVE_RUN_TYPE,
        "empirical_model_run": True,
        "eligible_for_performance_claims": True,
        "phase": "phase1-development-train-dev-only",
        "state": "awaiting_author_01_approval",
        "systems": LIVE_SYSTEMS,
        "current_fda_operational_availability": "not_operational",
        "expert_validated": False,
        "model_configuration": {
            "model": "gpt-5.5",
            "reasoning_effort": LIVE_REASONING_EFFORT,
            "temperature_requested": DIRECT_TEMPERATURE,
            "input_character_limit": LIVE_INPUT_CHARACTER_LIMIT,
            "input_counting_policy": (
                "model-facing system instructions, serialized case/evidence payload, and "
                "structured-output schema name are counted before dispatch"
            ),
            "final_structured_answer_token_limit": LIVE_FINAL_SCHEMA_TOKEN_LIMIT,
            "pilot_output_ceiling": LIVE_PILOT_OUTPUT_CEILING,
            "pilot_output_ceiling_status": "phase1_pilot_instrument_not_phase2_cap",
            "pre_live_deviation": "max_output_tokens raised from 800 to 25000 for reasoning",
            "retry_policy": "initial_attempt_plus_two_retries_unchanged_prompt_and_settings",
            "tokenizer": tokenizer_name,
        },
        "bundle": {
            "schema_version": bundle.schema_version,
            "exporter_version": bundle.exporter_version,
            "exporter_commit": "source-tree-state-recorded-in-artifact-digests",
            "benchmark_sha256": bundle.benchmark_sha256,
            "bundle_sha256": phase1_bundle_sha256(),
            "selected_input_hashes": bundle.selected_input_hashes,
            "cases": len(bundle.cases),
            "splits": {
                split: sum(case.split == split for case in bundle.cases)
                for split in PHASE1_ALLOWED_SPLITS
            },
        },
        "prompt_template_versions": {
            "direct_decision": DIRECT_DECISION_PROMPT_VERSION,
            "semantic_inspection": "1.0.0",
        },
        "prompt_template_digests": prompt_material,
        "frozen_prompt_digest": None,
        "frozen_configuration_digest": None,
        "phase2_controls": "prepared-but-not-active; explicit author-01 approval required",
        "schema_differences": {
            "B0_B1": "DirectDecisionOutput-v1",
            "RegBridge": "SemanticRiskOutput-v1 before deterministic synthesis",
        },
        "usage_summary": _usage_summary(outcomes),
        "phase2_cap_proposal": _phase2_cap(outcomes),
        "retry_log": [
            {
                "system": outcome.system,
                "case_id": outcome.case_id,
                "deviations": outcome.deviation_log,
            }
            for outcome in outcomes
            if outcome.deviation_log
        ],
        "invalid_outputs": [
            {
                "system": outcome.system,
                "case_id": outcome.case_id,
                "failure": outcome.failure,
            }
            for outcome in outcomes
            if outcome.outcome == "invalid_output"
        ],
        "digests": {
            "predictions_sha256": predictions_digest,
            "metrics_sha256": metrics_digest,
            "configuration_sha256": _digest_bytes(
                _canonical(
                    {
                        "model": "gpt-5.5",
                        "reasoning_effort": LIVE_REASONING_EFFORT,
                        "temperature": DIRECT_TEMPERATURE,
                        "pilot_output_ceiling": LIVE_PILOT_OUTPUT_CEILING,
                        "prompt_material": prompt_material,
                    }
                ).encode("utf-8")
            ),
        },
        "reports": [report.model_dump(mode="json") for report in reports],
        "openai_docs_sources": [
            "https://developers.openai.com/api/docs/models/gpt-5.5",
            "https://developers.openai.com/api/docs/guides/reasoning",
            "https://developers.openai.com/api/reference/cli/resources/responses/methods/create",
        ],
    }


async def run_phase1_live() -> Path:
    if not PHASE1_BUNDLE.is_file():
        write_phase1_bundle()
    bundle = load_phase1_bundle()
    _guard_phase1_cases(bundle.cases, location="bundle load")
    settings = _settings()
    tokenizer_name, counter = _token_counter(cast(str, settings.llm_model))
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    retriever = BM25Retriever(evidence)
    model = _model(settings, counter)
    case_by_id = _case_map(bundle)
    ordered_cases = tuple(case_by_id[case_input.case_id] for case_input in bundle.case_inputs)

    outcomes: list[LiveOutcome] = []
    first_request = True
    for system in LIVE_SYSTEMS:
        for case in ordered_cases:
            _guard_case(case, location=f"{system} dispatch")
            if system in {"B0", "B1"}:
                outcome = await _run_direct(
                    system=cast(Literal["B0", "B1"], system),
                    case=case,
                    bundle=bundle,
                    model=model,
                    evidence=evidence,
                    retriever=retriever,
                    first_authorized_request=first_request,
                )
            else:
                outcome = await _run_regbridge(
                    case=case,
                    bundle=bundle,
                    model=model,
                    first_authorized_request=first_request,
                )
            outcomes.append(outcome)
            if (
                first_request
                and outcome.attempts
                and outcome.attempts[-1].temperature_verification != "reported_match"
            ):
                return _write_artifacts(
                    bundle=bundle,
                    tokenizer_name=tokenizer_name,
                    outcomes=tuple(outcomes),
                    stopped_reason="temperature_compatibility_unconfirmed",
                )
            first_request = False
            if any(attempt.ceiling_hit for attempt in outcome.attempts):
                return _write_artifacts(
                    bundle=bundle,
                    tokenizer_name=tokenizer_name,
                    outcomes=tuple(outcomes),
                    stopped_reason="pilot_output_ceiling_hit",
                )
    _guard_phase1_cases(bundle.cases, location="scoring")
    return _write_artifacts(
        bundle=bundle,
        tokenizer_name=tokenizer_name,
        outcomes=tuple(outcomes),
        stopped_reason=None,
    )


def _write_artifacts(
    *,
    bundle: Phase1Bundle,
    tokenizer_name: str,
    outcomes: tuple[LiveOutcome, ...],
    stopped_reason: str | None,
) -> Path:
    run_id = f"m3-live-phase1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    result_dir = LIVE_RESULTS_ROOT / run_id
    paper_dir = LIVE_PAPER_ROOT / run_id
    valid_predictions = tuple(
        cast(SystemPrediction, outcome.prediction)
        for outcome in outcomes
        if outcome.prediction is not None
    )
    retrievals = tuple(outcome.retrieval for outcome in outcomes if outcome.retrieval is not None)
    reports: list[MetricsReport] = []
    case_rows: list[CaseEvaluation] = []
    for system in LIVE_SYSTEMS:
        completed_case_ids = {
            outcome.case_id for outcome in outcomes if outcome.system == system
        }
        system_cases = tuple(case for case in bundle.cases if case.case_id in completed_case_ids)
        system_predictions = tuple(pred for pred in valid_predictions if pred.system == system)
        system_traces = tuple(trace for trace in retrievals if trace and system == "B1")
        for scope, scoped_cases in (
            ("phase1-train", tuple(case for case in system_cases if case.split == "train")),
            (
                "phase1-development",
                tuple(case for case in system_cases if case.split == "development"),
            ),
            ("phase1-train-development", system_cases),
        ):
            scoped_case_ids = {case.case_id for case in scoped_cases}
            scoped_predictions = tuple(
                pred for pred in system_predictions if pred.case_id in scoped_case_ids
            )
            scored = _score_valid(
                cases=scoped_cases,
                predictions=scoped_predictions,
                retrieval_traces=system_traces,
                scope=scope,
                seed=LIVE_SEED,
            )
            if scored[0] is not None:
                reports.append(scored[0])
                case_rows.extend(scored[1])
    predictions_jsonl = _outcome_jsonl(outcomes)
    metrics_json = _metrics_json(tuple(reports), outcomes, bundle.cases)
    predictions_digest = _digest_bytes(predictions_jsonl.encode("utf-8"))
    metrics_digest = _digest_bytes(metrics_json.encode("utf-8"))
    manifest = _manifest(
        run_id=run_id,
        bundle=bundle,
        tokenizer_name=tokenizer_name,
        outcomes=outcomes,
        reports=tuple(reports),
        predictions_digest=predictions_digest,
        metrics_digest=metrics_digest,
    )
    if stopped_reason:
        manifest["stopped_reason"] = stopped_reason
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _atomic_write(result_dir / "manifest.json", manifest_json)
    _atomic_write(result_dir / "predictions.jsonl", predictions_jsonl)
    _atomic_write(result_dir / "metrics.json", metrics_json)
    _atomic_write(result_dir / "per-case.csv", _per_case_csv(outcomes))
    _atomic_write(
        result_dir / "attempts.jsonl",
        "".join(
            json.dumps(
                {
                    "system": outcome.system,
                    "case_id": outcome.case_id,
                    "attempt": attempt.to_json(),
                },
                sort_keys=True,
            )
            + "\n"
            for outcome in outcomes
            for attempt in outcome.attempts
        ),
    )
    _atomic_write(paper_dir / "m3-live-phase1-development-metrics.json", metrics_json)
    _atomic_write(paper_dir / "m3-live-phase1-development-per-case.csv", _per_case_csv(outcomes))
    return result_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M3 live Phase 1 on train/development only.")
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    if args.export_only:
        write_phase1_bundle()
        return
    result_dir = asyncio.run(run_phase1_live())
    print(f"Phase 1 live artifacts written to {result_dir.relative_to(REPOSITORY_ROOT).as_posix()}")
    print("State: awaiting_author_01_approval")


if __name__ == "__main__":
    main()
