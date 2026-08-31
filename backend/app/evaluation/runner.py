import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.baselines.direct import (
    DIRECT_INPUT_CHARACTER_LIMIT,
    DIRECT_MODEL_NAME,
    DIRECT_OUTPUT_TOKEN_LIMIT,
    DIRECT_TEMPERATURE,
)
from app.baselines.retrieval import BM25_CONFIGURATION
from app.baselines.runner import BaselineRunner
from app.config import REPOSITORY_ROOT
from app.domain.vocabulary import output_vocabulary
from app.evaluation.benchmark import FROZEN_BENCHMARK, load_frozen_benchmark
from app.evaluation.metrics import score_system
from app.evaluation.models import (
    CaseEvaluation,
    EvaluationArtifacts,
    EvaluationRun,
    MetricsReport,
    RetrievalTrace,
    SystemName,
    SystemPrediction,
)
from app.standards.evidence import EvidenceRegistry

CONFIGURATION_ID = "m3-fixture-all-systems-v1"
SYSTEMS: tuple[SystemName, ...] = ("B0", "B1", "B2", "RegBridge")
SEED = 20270829
FIXED_TIMESTAMP = "2026-08-30T00:00:00Z"
RUN_ID = "eval-m3-fixture-v1"
RESULT_DIRECTORY = REPOSITORY_ROOT / "results" / "validation" / RUN_ID
PAPER_DIRECTORY = REPOSITORY_ROOT / "paper" / "tables" / "validation"
PAPER_DETERMINISTIC_DIRECTORY = REPOSITORY_ROOT / "paper" / "tables" / "deterministic"
PAPER_RETRIEVAL_DIRECTORY = REPOSITORY_ROOT / "paper" / "tables" / "retrieval"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _tree_digest() -> str:
    excluded_parts = {
        ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".vite", "dist", "coverage", "htmlcov",
        "results", "tables", "figures",
    }
    digest = hashlib.sha256()
    paths: list[Path] = []

    def fail_on_walk_error(error: OSError) -> None:
        raise error

    for directory, directories, filenames in os.walk(
        REPOSITORY_ROOT, onerror=fail_on_walk_error
    ):
        directories[:] = [
            name for name in directories
            if name not in excluded_parts and not name.endswith(".egg-info")
        ]
        for name in filenames:
            if (
                (name.startswith(".env") and name != ".env.example")
                or name in {".coverage", "Thumbs.db", ".DS_Store"}
                or name.endswith((".pyc", ".log", ".tsbuildinfo", ".sqlite", ".sqlite3", ".db"))
            ):
                continue
            paths.append(Path(directory) / name)
    for path in sorted(paths, key=lambda item: item.relative_to(REPOSITORY_ROOT).as_posix()):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _combined_digest(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(REPOSITORY_ROOT).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


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


def _jsonl(items: tuple[Any, ...]) -> str:
    return "".join(
        json.dumps(item.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
        for item in items
    )


def _per_case_csv(
    cases: tuple[CaseEvaluation, ...], predictions: tuple[SystemPrediction, ...]
) -> str:
    prediction_map = {(item.system, item.case_id): item for item in predictions}
    output = io.StringIO(newline="")
    fields = (
        "system",
        "case_id",
        "split",
        "fixture_family",
        "reference_decision",
        "prediction_decision",
        "reference_action",
        "prediction_action",
        "unsafe_false_negative",
        "review_bypass",
        "conservative_false_positive",
        "correct",
        "evidence_ids",
        "rule_ids",
        "prediction_source",
        "result_status",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in cases:
        prediction = prediction_map[(item.system, item.case_id)]
        row = item.model_dump(mode="json")
        row.update(
            {
                "evidence_ids": ";".join(prediction.evidence_ids),
                "rule_ids": ";".join(prediction.rule_ids),
                "prediction_source": prediction.prediction_source,
                "result_status": (
                    "genuine deterministic experimental output"
                    if item.system == "B2" else "fixture validation only"
                ),
            }
        )
        writer.writerow(row)
    return output.getvalue()


def _metrics_csv(reports: tuple[MetricsReport, ...]) -> str:
    output = io.StringIO(newline="")
    fields = (
        "system",
        "scope",
        "result_status",
        "interval_interpretation",
        "run_type",
        "empirical_model_run",
        "eligible_for_performance_claims",
        "expert_validated",
        "current_fda_operational_availability",
        "unsafe_fn_numerator",
        "unsafe_fn_denominator",
        "unsafe_fn_rate",
        "unsafe_fn_wilson_low",
        "unsafe_fn_wilson_high",
        "high_blocking_unsafe_fn_rate",
        "review_bypass_rate",
        "review_bypass_numerator",
        "review_bypass_denominator",
        "outside_represented_count",
        "outside_represented_rate",
        "outside_counts_by_decision",
        "outside_rates_by_decision",
        "sensitivity_only_accuracy_excluding_outside",
        "sensitivity_only_included_count",
        "safety_caveat",
        "conservative_false_positive_rate",
        "macro_f1",
        "accuracy",
        "balanced_accuracy",
        "heading_mapping_accuracy",
        "evidence_citation_accuracy",
        "repair_action_accuracy",
        "abstention_accuracy",
        "bm25_recall_at_3",
        "bm25_precision_at_3",
        "bm25_mrr",
        "requests",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "action_required_family_count",
        "families_with_unsafe_misses",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for report in reports:
        unsafe = report.unsafe_false_negative_rate
        retrieval = report.retrieval
        writer.writerow(
            {
                "system": report.system,
                "scope": report.scope,
                "result_status": report.result_status,
                "interval_interpretation": report.interval_interpretation,
                "run_type": "deterministic_fixture_validation",
                "empirical_model_run": False,
                "eligible_for_performance_claims": False,
                "expert_validated": False,
                "current_fda_operational_availability": "not_operational",
                "unsafe_fn_numerator": unsafe.numerator,
                "unsafe_fn_denominator": unsafe.denominator,
                "unsafe_fn_rate": unsafe.rate,
                "unsafe_fn_wilson_low": unsafe.wilson_95_low if report.system == "B2" else None,
                "unsafe_fn_wilson_high": unsafe.wilson_95_high if report.system == "B2" else None,
                "high_blocking_unsafe_fn_rate": (
                    report.high_blocking_unsafe_false_negative_rate.rate
                ),
                "review_bypass_rate": report.review_bypass_rate.rate,
                "review_bypass_numerator": report.review_bypass_rate.numerator,
                "review_bypass_denominator": report.review_bypass_rate.denominator,
                "outside_represented_count": report.vocabulary_diagnostic.outside_represented_count,
                "outside_represented_rate": report.vocabulary_diagnostic.outside_represented_rate,
                "outside_counts_by_decision": json.dumps(
                    report.vocabulary_diagnostic.outside_counts_by_decision, sort_keys=True
                ),
                "outside_rates_by_decision": json.dumps(
                    report.vocabulary_diagnostic.outside_rates_by_decision, sort_keys=True
                ),
                "sensitivity_only_accuracy_excluding_outside": (
                    report.vocabulary_diagnostic.accuracy_excluding_outside_predictions
                ),
                "sensitivity_only_included_count": (
                    report.vocabulary_diagnostic.sensitivity_included_count
                ),
                "safety_caveat": report.vocabulary_diagnostic.safety_caveat,
                "conservative_false_positive_rate": (report.conservative_false_positive_rate.rate),
                "macro_f1": report.macro_f1,
                "accuracy": report.accuracy,
                "balanced_accuracy": report.balanced_accuracy,
                "heading_mapping_accuracy": report.heading_mapping_accuracy,
                "evidence_citation_accuracy": report.evidence_citation_accuracy,
                "repair_action_accuracy": report.repair_action_accuracy,
                "abstention_accuracy": report.abstention_accuracy,
                "bm25_recall_at_3": retrieval.recall_at_3 if retrieval else None,
                "bm25_precision_at_3": retrieval.precision_at_3 if retrieval else None,
                "bm25_mrr": retrieval.mrr if retrieval else None,
                "requests": report.requests,
                "input_tokens": report.input_tokens,
                "output_tokens": report.output_tokens,
                "cost_usd": report.cost_usd,
                "action_required_family_count": report.action_required_family_count,
                "families_with_unsafe_misses": report.families_with_unsafe_misses,
            }
        )
    return output.getvalue()


def _retrieval_csv(reports: tuple[MetricsReport, ...]) -> str:
    output = io.StringIO(newline="")
    fields = (
        "system", "scope", "result_status", "evaluated_cases", "recall_at_3",
        "precision_at_3", "mrr", "expert_validated", "current_fda_operational_availability",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for report in reports:
        if report.system != "B1" or report.retrieval is None:
            continue
        writer.writerow({
            "system": "B1 BM25 retrieval",
            "scope": report.scope,
            **report.retrieval.model_dump(),
            "expert_validated": False,
            "current_fda_operational_availability": "not_operational",
        })
    return output.getvalue()


def _summary(reports: tuple[MetricsReport, ...]) -> str:
    lines = [
        "# M3 deterministic fixture validation",
        "",
        "> These outputs are `deterministic_fixture_validation`, not empirical model results, "
        "and are ineligible for RegBridge-superiority or model-performance claims. Only B2 is "
        "a genuine rule-only experimental output. FDA availability remains `not_operational`.",
        "",
        "Labels are controlled prospective `author_adjudicated_for_demo` research labels with "
        "`expert_validated: false`.",
        "",
        "## M3 harness validation: 12 held-out cases",
        "",
        "B0/B1/RegBridge decision scores confirm harness and contract execution only. "
        "They are not empirical results and must not enter the paper's empirical results table.",
        "",
        "| System | Result status | Unsafe FNR (n/N) | Wilson 95% (B2 only) | "
        "Review bypass | Macro-F1 | Accuracy |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for report in reports:
        if report.scope != "held-out-test":
            continue
        unsafe = report.unsafe_false_negative_rate
        interval = (
            f"{unsafe.wilson_95_low:.3f}-{unsafe.wilson_95_high:.3f}"
            if report.system == "B2" else "not interpreted"
        )
        lines.append(
            f"| {report.system} | {report.result_status} | "
            f"{unsafe.rate:.3f} ({unsafe.numerator}/{unsafe.denominator}) "
            f"| {interval} | {report.review_bypass_rate.rate:.3f} | "
            f"{report.macro_f1:.3f} | {report.accuracy:.3f} |"
        )
    lines.extend(
        (
            "",
            "Wilson and bootstrap calculations for canned outputs are retained only in raw "
            "scorer data for testing; they have no statistical interpretation. B2 intervals "
            "are exploratory only. No independence or significance claims are made.",
            "All six non-overlapping held-out families are included in cluster resampling; "
            "zero-denominator replicates are omitted.",
            "",
            "| System | Result status | Held-out family | Unsafe misses | Action-required cases |",
            "|---|---|---|---:|---:|",
        )
    )
    for report in reports:
        if report.scope == "held-out-test":
            for family in report.family_sensitivity:
                lines.append(
                    f"| {report.system} | {report.result_status} | {family.fixture_family} | "
                    f"{family.unsafe_misses} | "
                    f"{family.eligible_cases} |"
                )
    for report in reports:
        if report.system == "B2" and report.scope == "held-out-test":
            lines.extend((
                "",
                f"B2 unsafe misses occurred in {report.families_with_unsafe_misses} of the "
                f"{report.action_required_family_count} held-out families containing "
                "action-required cases (six held-out families total).",
            ))
    lines.extend((
        "",
        "## Measured B1 BM25 retrieval — held-out cases",
        "",
        "These are actual deterministic retrieval measurements, separate from B1's "
        "non-empirical end-to-end decision accuracy. Cases without an official relevant span "
        "in the six-span corpus are excluded from retrieval denominators.",
        "",
        "| Component | Result status | Evaluated cases | Recall@3 | Precision@3 | MRR |",
        "|---|---|---:|---:|---:|---:|",
    ))
    for report in reports:
        if report.system == "B1" and report.scope == "held-out-test" and report.retrieval:
            retrieval = report.retrieval
            lines.append(
                f"| B1 BM25 | {retrieval.result_status} | {retrieval.evaluated_cases} | "
                f"{retrieval.recall_at_3:.3f} | {retrieval.precision_at_3:.3f} | "
                f"{retrieval.mrr:.3f} |"
            )
    lines.extend(
        (
            "",
            "## Secondary diagnostic: all 30 cases",
            "",
            "| System | Result status | Unsafe FNR | Review bypass | Macro-F1 | Accuracy |",
            "|---|---|---:|---:|---:|---:|",
        )
    )
    for report in reports:
        if report.scope != "all-cases-secondary":
            continue
        lines.append(
            f"| {report.system} | {report.result_status} | "
            f"{report.unsafe_false_negative_rate.rate:.3f} | "
            f"{report.review_bypass_rate.rate} | "
            f"{report.macro_f1:.3f} | {report.accuracy:.3f} |"
        )
    lines.extend((
        "", "## Vocabulary disclosure (sensitivity only; never an alternative headline)", "",
        "| System | Scope | Outside / valid | Counts by predicted class | "
        "Rates by predicted class | Sensitivity-only accuracy excluding outside |",
        "|---|---|---|---|---|---|",
    ))
    for report in reports:
        diagnostic = report.vocabulary_diagnostic
        lines.append(
            f"| {report.system} | {report.scope} | {diagnostic.outside_represented_count}/"
            f"{diagnostic.valid_prediction_count} ({diagnostic.outside_represented_rate}) | "
            f"{json.dumps(diagnostic.outside_counts_by_decision, sort_keys=True)} | "
            f"{json.dumps(diagnostic.outside_rates_by_decision, sort_keys=True)} | "
            f"{diagnostic.accuracy_excluding_outside_predictions} |"
        )
        if diagnostic.safety_caveat:
            lines.append(f"\n{report.system} ({report.scope}): {diagnostic.safety_caveat}\n")
    lines.append("")
    return "\n".join(lines)


def _manifest(
    *,
    predictions_digest: str,
    metrics_digest: str,
    runner: BaselineRunner,
) -> dict[str, Any]:
    standards = (
        REPOSITORY_ROOT / "data" / "standards" / "manifest.yaml",
        REPOSITORY_ROOT / "data" / "standards" / "operational-status.yaml",
    )
    rules = (
        REPOSITORY_ROOT / "data" / "rules" / "heading-rules.yaml",
        REPOSITORY_ROOT / "data" / "rules" / "metadata-rules.yaml",
    )
    evidence = (REPOSITORY_ROOT / "data" / "standards" / "evidence.yaml",)
    prompt_config = {
        "shared_direct_schema": "DirectDecisionOutput-v1",
        "shared_model": DIRECT_MODEL_NAME,
        "temperature": DIRECT_TEMPERATURE,
        "input_character_limit": DIRECT_INPUT_CHARACTER_LIMIT,
        "over_limit_behavior": "fail-validation",
        "output_token_limit": DIRECT_OUTPUT_TOKEN_LIMIT,
        "usage_measurement": "synthetic-character-estimates-not-provider-token-usage",
        "latency_measurement": "fixed-zero-fixture-placeholder-not-runtime-measurement",
        "case_serialization": "identical-for-b0-b1",
        "evidence_ordering": "evidence-id-ascending",
        "regbridge_schema_difference": (
            "RegBridge uses the existing evidence-bounded SemanticRiskOutput schema before "
            "deterministic synthesis."
        ),
    }
    retrieval_config = {
        **BM25_CONFIGURATION,
        "corpus_sha256": runner.retriever.corpus_sha256,
        "configuration_sha256": runner.retriever.configuration_sha256,
    }
    configuration = {
        "configuration_id": CONFIGURATION_ID,
        "systems": SYSTEMS,
        "headline_split": "test",
        "secondary_scope": "all-30",
        "seed": SEED,
        "network_required": False,
    }
    return {
        "manifest_version": "1.0.0",
        "run_id": RUN_ID,
        "created_at": FIXED_TIMESTAMP,
        "run_type": "deterministic_fixture_validation",
        "empirical_model_run": False,
        "eligible_for_performance_claims": False,
        "genuine_experimental_systems": ["B2"],
        "shared_output_vocabulary": output_vocabulary(),
        "architecture_disclosure": {
            "regbridge_rule_set_structurally_emits": [
                "REUSE_WITH_NEW_CONTEXT", "REUSE_AS_LEGACY_REFERENCE", "HUMAN_REGULATORY_REVIEW",
            ],
            "permitted_schema_decisions": "all six; no benchmark-distribution restriction",
            "benchmark_taxonomy": "three represented reference classes",
        },
        "synthetic_contract_fixture_systems": ["B0", "B1", "RegBridge"],
        "result_status_by_system": {
            system: (
                "genuine deterministic experimental output"
                if system == "B2" else "fixture validation only"
            ) for system in SYSTEMS
        },
        "retrieval_measurements": {
            "system": "B1",
            "result_status": "genuine deterministic retrieval measurement",
            "metrics": ["recall_at_3", "precision_at_3", "mrr"],
            "end_to_end_decision_scores_are_empirical": False,
        },
        "canned_interval_use": "scorer validation only; no statistical interpretation",
        "current_fda_operational_availability": "not_operational",
        "expert_validated": False,
        "claims_boundary": (
            "No model-comparison or RegBridge-superiority claim is permitted without a later "
            "declared live-model run."
        ),
        "digests": {
            "source_tree_sha256": _tree_digest(),
            "benchmark_sha256": _file_digest(FROZEN_BENCHMARK),
            "standards_sha256": _combined_digest(standards),
            "evidence_sha256": _combined_digest(evidence),
            "rules_sha256": _combined_digest(rules),
            "graph_sha256": _digest_bytes(_canonical(runner.graph_snapshots).encode("utf-8")),
            "prompt_sha256": _digest_bytes(
                _canonical({
                    "configuration": prompt_config,
                    "direct_template_source": _file_digest(
                        REPOSITORY_ROOT / "backend/app/baselines/direct.py"
                    ),
                    "semantic_template_source": _file_digest(
                        REPOSITORY_ROOT / "backend/app/analyzer/service.py"
                    ),
                }).encode("utf-8")
            ),
            "retrieval_sha256": _digest_bytes(_canonical(retrieval_config).encode("utf-8")),
            "configuration_sha256": _digest_bytes(_canonical(configuration).encode("utf-8")),
            "prediction_content_sha256": predictions_digest,
            "metrics_content_sha256": metrics_digest,
        },
        "prompt_configuration": prompt_config,
        "graph_snapshot_digests": {
            key: _digest_bytes(_canonical(snapshot).encode("utf-8"))
            for key, snapshot in sorted(runner.graph_snapshots.items())
        },
        "retrieval_configuration": retrieval_config,
        "evaluation_configuration": configuration,
        "statistical_scope": (
            "Headline results use 12 held-out cases across six non-overlapping fixture "
            "families. B2 intervals are exploratory. Intervals for canned outputs are scorer "
            "validation only and have no statistical interpretation. No independence or "
            "significance claims are made."
        ),
    }


def run_evaluation(configuration_id: str = CONFIGURATION_ID) -> EvaluationRun:
    if configuration_id != CONFIGURATION_ID:
        raise ValueError("evaluation configuration is not allowlisted")
    benchmark = load_frozen_benchmark()
    runner = BaselineRunner()
    inputs = {case.case_id: runner.case_input(case) for case in benchmark.cases}
    predictions: list[SystemPrediction] = []
    retrieval_traces: list[RetrievalTrace] = []
    for system in SYSTEMS:
        for case_id in sorted(inputs):
            prediction, retrieval = runner.run(system, inputs[case_id])
            predictions.append(prediction)
            if retrieval:
                retrieval_traces.append(retrieval)
    prediction_tuple = tuple(predictions)
    trace_tuple = tuple(retrieval_traces)

    regulatory_ids = frozenset(item.id for item in EvidenceRegistry().load())
    reports: list[MetricsReport] = []
    case_rows: list[CaseEvaluation] = []
    for system in SYSTEMS:
        system_predictions = tuple(item for item in prediction_tuple if item.system == system)
        system_traces = tuple(item for item in trace_tuple if item.system == system)
        held_out = tuple(item for item in benchmark.cases if item.split == "test")
        held_predictions = tuple(
            item
            for item in system_predictions
            if inputs[item.case_id].case_id in {c.case_id for c in held_out}
        )
        held_traces = tuple(
            item for item in system_traces if item.case_id in {c.case_id for c in held_out}
        )
        headline, _ = score_system(
            cases=held_out,
            predictions=held_predictions,
            retrieval_traces=held_traces,
            scope="held-out-test",
            seed=SEED,
            regulatory_evidence_ids=regulatory_ids,
        )
        diagnostic, evaluations = score_system(
            cases=benchmark.cases,
            predictions=system_predictions,
            retrieval_traces=system_traces,
            scope="all-cases-secondary",
            seed=SEED,
            regulatory_evidence_ids=regulatory_ids,
        )
        reports.extend((headline, diagnostic))
        case_rows.extend(evaluations)

    report_tuple = tuple(reports)
    case_tuple = tuple(case_rows)
    prediction_jsonl = _jsonl(prediction_tuple)
    retrieval_jsonl = _jsonl(trace_tuple)
    metrics_json = (
        json.dumps(
            {"reports": [item.model_dump(mode="json") for item in report_tuple]},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    per_case_csv = _per_case_csv(case_tuple, prediction_tuple)
    metrics_csv = _metrics_csv(report_tuple)
    summary = _summary(report_tuple)
    predictions_digest = _digest_bytes(prediction_jsonl.encode("utf-8"))
    metrics_digest = _digest_bytes(metrics_json.encode("utf-8"))
    manifest_json = (
        json.dumps(
            _manifest(
                predictions_digest=predictions_digest,
                metrics_digest=metrics_digest,
                runner=runner,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    paths = {
        "manifest": RESULT_DIRECTORY / "manifest.json",
        "predictions": RESULT_DIRECTORY / "predictions.jsonl",
        "retrieval": RESULT_DIRECTORY / "retrieval-traces.jsonl",
        "per_case": RESULT_DIRECTORY / "per-case.csv",
        "metrics_json": RESULT_DIRECTORY / "metrics.json",
        "metrics_csv": RESULT_DIRECTORY / "metrics.csv",
        "summary": RESULT_DIRECTORY / "SUMMARY.md",
        "paper": PAPER_DIRECTORY / "m3-held-out-validation.csv",
        "paper_deterministic": PAPER_DETERMINISTIC_DIRECTORY / "m3-b2-held-out.csv",
        "paper_retrieval": PAPER_RETRIEVAL_DIRECTORY / "m3-bm25-held-out.csv",
    }
    for path, content in (
        (paths["manifest"], manifest_json),
        (paths["predictions"], prediction_jsonl),
        (paths["retrieval"], retrieval_jsonl),
        (paths["per_case"], per_case_csv),
        (paths["metrics_json"], metrics_json),
        (paths["metrics_csv"], metrics_csv),
        (paths["summary"], summary),
        (
            paths["paper"],
            _metrics_csv(tuple(item for item in report_tuple if item.scope == "held-out-test")),
        ),
        (
            paths["paper_deterministic"],
            _metrics_csv(tuple(
                item for item in report_tuple
                if item.scope == "held-out-test" and item.system == "B2"
            )),
        ),
        (
            paths["paper_retrieval"],
            _retrieval_csv(tuple(item for item in report_tuple if item.scope == "held-out-test")),
        ),
    ):
        _atomic_write(path, content)

    artifacts = EvaluationArtifacts(
        run_directory=RESULT_DIRECTORY.relative_to(REPOSITORY_ROOT).as_posix(),
        manifest_json=paths["manifest"].relative_to(REPOSITORY_ROOT).as_posix(),
        predictions_jsonl=paths["predictions"].relative_to(REPOSITORY_ROOT).as_posix(),
        retrieval_jsonl=paths["retrieval"].relative_to(REPOSITORY_ROOT).as_posix(),
        per_case_csv=paths["per_case"].relative_to(REPOSITORY_ROOT).as_posix(),
        metrics_json=paths["metrics_json"].relative_to(REPOSITORY_ROOT).as_posix(),
        metrics_csv=paths["metrics_csv"].relative_to(REPOSITORY_ROOT).as_posix(),
        summary_markdown=paths["summary"].relative_to(REPOSITORY_ROOT).as_posix(),
        paper_table_csv=paths["paper"].relative_to(REPOSITORY_ROOT).as_posix(),
        paper_deterministic_table_csv=(
            paths["paper_deterministic"].relative_to(REPOSITORY_ROOT).as_posix()
        ),
        paper_retrieval_table_csv=paths["paper_retrieval"].relative_to(REPOSITORY_ROOT).as_posix(),
        prediction_content_sha256=predictions_digest,
        metrics_content_sha256=metrics_digest,
    )
    run = EvaluationRun(
        id=RUN_ID,
        configuration_id=CONFIGURATION_ID,
        state="completed",
        run_type="deterministic_fixture_validation",
        empirical_model_run=False,
        eligible_for_performance_claims=False,
        current_fda_operational_availability="not_operational",
        systems=SYSTEMS,
        seed=SEED,
        created_at=FIXED_TIMESTAMP,
        updated_at=FIXED_TIMESTAMP,
        metrics=report_tuple,
        cases=case_tuple,
        artifacts=artifacts,
    )
    _atomic_write(
        RESULT_DIRECTORY / "run.json",
        json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return run
