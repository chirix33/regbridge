import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import REPOSITORY_ROOT
from app.presentation.models import (
    DemoPreset,
    M4PresentationSnapshot,
    PresentationCasePrediction,
    PresentationCaseTrace,
    PresentationMetricReport,
    PresentationRate,
)
from app.presentation.repository import SNAPSHOT_PATH, SNAPSHOT_VERSION, compute_snapshot_sha256

SOURCE_RUN_ID = "m3-live-phase2-20260901T170811002109Z"
SOURCE_RUN_DIR = REPOSITORY_ROOT / "results" / "live" / SOURCE_RUN_ID
EXPECTED_SOURCE_HASHES = {
    "manifest.json": "048532089ada46969adc50f5adf4746d3f287fb7b67baec2db10329dd0d62ee5",
    "metrics.json": "1640cf2053dfb21d8a7e20bb6c544b29ac71fad3fb6ccfd61435283b5cfd58ae",
    "per-case.csv": "a8e03c7ab09caac55ad70326cc3b44f815210e46328f4c1bddd87063c5a64929",
    "predictions.jsonl": "1c1c2e76408fd3a3c19c92e19b34642f9b4b1f9093fb82a9a54fd1dd5e1c0e22",
    "retrieval.jsonl": "b3784eaa4f1a04cac66b3554105b67f305e3106d8789a2758c6cb54e1b5d229b",
    "b2-held-out-rescore.json": "c7f4f3461d5131843a5241902bcb7aceb375fe8210ac76dfbb244124582d3e19",
    "completion-audit.json": "586b9b9004c223db8d4bc6e29fcfbac6a0e2604ed9dd1dce49a44f98a01ef3d1",
}
HELD_OUT_BUNDLE = (
    REPOSITORY_ROOT / "data" / "benchmark" / "phase2" / "benchmark-held-out-v1.0.0.json"
)
CORRECTION_LEDGER = (
    REPOSITORY_ROOT
    / "data"
    / "presentation"
    / "m4"
    / SNAPSHOT_VERSION
    / "presentation-corrections.md"
)
REPRESENTED = {
    "REUSE_WITH_NEW_CONTEXT",
    "REUSE_AS_LEGACY_REFERENCE",
    "HUMAN_REGULATORY_REVIEW",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def verify_sources() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for filename, expected in EXPECTED_SOURCE_HASHES.items():
        path = SOURCE_RUN_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing source artifact: {filename}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"source artifact changed: {filename}")
        hashes[filename] = actual
    return hashes


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _rate(metric: dict[str, Any]) -> PresentationRate:
    return PresentationRate(
        numerator=int(metric["numerator"]),
        denominator=int(metric["denominator"]),
        rate=metric.get("rate"),
    )


def _invalid_count(
    metrics: dict[str, Any], repetition: int | None, system: str
) -> tuple[int, float]:
    if repetition is None or system == "B2":
        return 0, 0.0
    diagnostic = metrics["invalid_output_diagnostics"][str(repetition)][system]
    return int(diagnostic["invalid_outputs"]), float(diagnostic["failure_rate"])


def _report(
    report: dict[str, Any], metrics: dict[str, Any], repetition: int | None
) -> PresentationMetricReport:
    invalid_count, invalid_rate = _invalid_count(metrics, repetition, report["system"])
    return PresentationMetricReport(
        system=report["system"],
        repetition_index=repetition,
        result_status=report["result_status"],
        accuracy=report["accuracy"],
        macro_f1=report["macro_f1"],
        unsafe_false_negative_rate=_rate(report["unsafe_false_negative_rate"]),
        review_bypass_rate=_rate(report["review_bypass_rate"]),
        outside_represented_rate=report["vocabulary_diagnostic"]["outside_represented_rate"],
        invalid_outputs=invalid_count,
        invalid_output_rate=invalid_rate,
        requests=report["requests"],
        input_tokens=report["input_tokens"],
        output_tokens=report["output_tokens"],
        latency_ms_total=report["latency_ms_total"],
        cost_usd=report.get("cost_usd"),
        retrieval=report.get("retrieval"),
        family_sensitivity=tuple(report.get("family_sensitivity") or ()),
    )


def _load_prediction_records() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with (SOURCE_RUN_DIR / "predictions.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _load_per_case_flags() -> dict[tuple[int, str, str], dict[str, Any]]:
    rows: dict[tuple[int, str, str], dict[str, Any]] = {}
    with (SOURCE_RUN_DIR / "per-case.csv").open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[(int(row["repetition_index"]), row["system"], row["case_id"])] = row
    return rows


def _build_case_predictions(
    records: list[dict[str, Any]],
    flags: dict[tuple[int, str, str], dict[str, Any]],
    b2_predictions: list[dict[str, Any]],
    references: dict[str, dict[str, Any]],
) -> dict[str, list[PresentationCasePrediction]]:
    grouped: dict[str, list[PresentationCasePrediction]] = {}
    for record in records:
        prediction = record["prediction"]
        row = flags[(record["repetition_index"], record["system"], record["case_id"])]
        grouped.setdefault(record["case_id"], []).append(
            PresentationCasePrediction(
                system=record["system"],
                repetition_index=record["repetition_index"],
                result_status="live model output",
                outcome=record["outcome"],
                decision=prediction["decision"],
                action=prediction["action"],
                human_review_required=prediction["human_review_required"],
                evidence_ids=tuple(prediction.get("evidence_ids") or ()),
                rule_ids=tuple(prediction.get("rule_ids") or ()),
                unsafe_false_negative=row.get("unsafe_false_negative", "").lower() == "true",
                review_bypass=row.get("review_bypass", "").lower() == "true",
                outside_represented_class=prediction["decision"] not in REPRESENTED,
                cost_usd=prediction.get("cost_usd"),
                latency_ms=prediction["latency_ms"],
                requests=prediction["requests"],
                failure=record.get("failure"),
            )
        )
    for prediction in b2_predictions:
        reference = references[prediction["case_id"]]
        action_required = (
            reference["decision"] != "REUSE_AS_LEGACY_REFERENCE"
            or reference["action"] != "NO_MATERIAL_REPAIR"
            or reference["human_review_required"]
        )
        is_human_reference = reference["decision"] == "HUMAN_REGULATORY_REVIEW"
        grouped.setdefault(prediction["case_id"], []).append(
            PresentationCasePrediction(
                system="B2",
                repetition_index=None,
                result_status="genuine deterministic experimental output",
                outcome="valid_prediction",
                decision=prediction["decision"],
                action=prediction["action"],
                human_review_required=prediction["human_review_required"],
                evidence_ids=tuple(prediction.get("evidence_ids") or ()),
                rule_ids=tuple(prediction.get("rule_ids") or ()),
                unsafe_false_negative=action_required
                and prediction["decision"] == "REUSE_AS_LEGACY_REFERENCE"
                and prediction["unconditional_reuse"],
                review_bypass=is_human_reference
                and prediction["decision"] != "HUMAN_REGULATORY_REVIEW"
                and not prediction["human_review_required"],
                outside_represented_class=prediction["decision"] not in REPRESENTED,
                cost_usd=prediction.get("cost_usd"),
                latency_ms=prediction["latency_ms"],
                requests=prediction["requests"],
                failure=prediction.get("failure"),
            )
        )
    for predictions in grouped.values():
        predictions.sort(key=lambda item: (item.system, item.repetition_index or 0))
    return grouped


def _demo_presets() -> tuple[DemoPreset, ...]:
    return (
        DemoPreset(
            id="m4-case-a-primary",
            route="/demo/case-a",
            label="Case A: removed 3.2.S.1.2 placement",
            fixture_id="case-a-removed-3212",
            purpose="Identifier reuse with new context group and legacy suspension.",
            primary_path=True,
            scenario_mode="prospective_forward_compatibility",
        ),
        DemoPreset(
            id="m4-case-c-primary",
            route="/demo/case-c",
            label="Case C: stale applicant mismatch",
            fixture_id="case-c-stale-applicant",
            purpose="Rules-only reuse contrasted with RegBridge human-review escalation.",
            primary_path=True,
            scenario_mode="prospective_forward_compatibility",
        ),
        DemoPreset(
            id="m4-case-b-contingency",
            route="/demo/case-b",
            label="Case B: lifecycle-sensitive manufacturer metadata",
            fixture_id="case-b-normalize-all",
            purpose="Metadata normalization and ambiguity variants for reviewer questions.",
            primary_path=False,
            scenario_mode="prospective_forward_compatibility",
            metadata_plan={
                "intent": "normalize-metadata",
                "manufacturer_partitioning": "unnecessary",
                "replacement_manufacturer_value": None,
            },
        ),
    )


def build_snapshot() -> M4PresentationSnapshot:
    source_hashes = verify_sources()
    manifest = _read_json(SOURCE_RUN_DIR / "manifest.json")
    metrics = _read_json(SOURCE_RUN_DIR / "metrics.json")
    audit = _read_json(SOURCE_RUN_DIR / "completion-audit.json")
    bundle = _read_json(HELD_OUT_BUNDLE)
    b2 = _read_json(SOURCE_RUN_DIR / "b2-held-out-rescore.json")
    records = _load_prediction_records()
    flags = _load_per_case_flags()
    references = {case["case_id"]: case["reference"] for case in bundle["cases"]}
    predictions_by_case = _build_case_predictions(records, flags, b2["predictions"], references)

    reports = [
        _report(item["report"], metrics, item["repetition_index"])
        for item in metrics["per_repetition_reports"]
    ]
    reports.append(_report(metrics["b2_report"], metrics, None))

    cases: list[PresentationCaseTrace] = []
    for case in bundle["cases"]:
        predictions = tuple(predictions_by_case[case["case_id"]])
        live_decisions = {
            (prediction.system, prediction.decision, prediction.action)
            for prediction in predictions
            if prediction.repetition_index is not None
        }
        cases.append(
            PresentationCaseTrace(
                case_id=case["case_id"],
                fixture_id=case["fixture_id"],
                fixture_family=case["fixture_family"],
                archetype=case["archetype"],
                split=case["split"],
                selected_leaf_id=case["selected_leaf_id"],
                reference_decision=case["reference"]["decision"],
                reference_action=case["reference"]["action"],
                reference_severity=case["reference"]["severity"],
                reference_human_review_required=case["reference"]["human_review_required"],
                mutation=case["mutation"],
                package_sha256=case["package_sha256"],
                selected_file_sha256=case["selected_file_sha256"],
                decision_fingerprint_sha256=case["decision_fingerprint_sha256"],
                predictions=predictions,
                varied_predictions=len(live_decisions) > len(
                    {prediction.system for prediction in predictions if prediction.repetition_index}
                ),
            )
        )

    b1_retrieval_reports: list[tuple[int, dict[str, Any]]] = []
    for report in reports:
        if report.system == "B1" and report.repetition_index is not None and report.retrieval:
            b1_retrieval_reports.append((report.repetition_index, report.retrieval))
    retrieval_summary = {
        "result_status": "genuine deterministic retrieval measurement",
        "per_repetition": [
            {
                "repetition_index": repetition_index,
                "recall_at_3": retrieval["recall_at_3"],
                "precision_at_3": retrieval["precision_at_3"],
                "mrr": retrieval["mrr"],
                "evaluated_cases": retrieval["evaluated_cases"],
            }
            for repetition_index, retrieval in b1_retrieval_reports
        ],
    }
    snapshot = M4PresentationSnapshot(
        schema_version="m4.presentation.v1",
        snapshot_version=SNAPSHOT_VERSION,
        source_run_id=SOURCE_RUN_ID,
        source_run_directory="results/live/m3-live-phase2-20260901T170811002109Z",
        source_run_file_sha256=source_hashes,
        repository_commit=_git_commit(),
        benchmark_sha256=bundle["benchmark_sha256"],
        frozen_prompt_digest=manifest["frozen_prompt_digest"],
        frozen_configuration_digest=manifest["frozen_configuration_digest"],
        generated_from={
            "generator": "backend.app.presentation.generate",
            "source": "frozen Phase 2 live artifacts",
            "mode": "presentation-only derived snapshot",
        },
        run_type="live_model_run",
        empirical_model_run=True,
        eligible_for_performance_claims=True,
        current_fda_operational_availability="not_operational",
        expert_validated=False,
        headline_scope="held-out-test",
        disclosure=(
            f"Presentation snapshot derived from frozen Phase 2 run {SOURCE_RUN_ID}; "
            "results are displayed, not recomputed."
        ),
        limitations=(
            "FDA/CDER controlled prospective research scenario only.",
            "FDA eCTD v4.0 forward compatibility remains not_operational.",
            "Labels and rules are author-adjudicated for the demo, expert_validated: false.",
            "Live-mode outputs claim configuration and artifact reproducibility only.",
            "Clustered intervals are exploratory and make no independence or significance claim.",
        ),
        completion_audit={
            "state": audit["state"],
            "stop_reason": audit["stop_reason"],
            "integrity_audit_passed": audit["integrity_audit_passed"],
            "scheduled_outcomes": audit["scheduled_outcomes"],
            "completed_outcomes": audit["completed_outcomes"],
            "truncation_count": audit["truncation_count"],
        },
        metric_reports=tuple(reports),
        metric_ranges=metrics["metric_ranges"],
        retrieval_summary=retrieval_summary,
        usage_summary=audit["usage"]["overall"],
        cost_summary={
            "total_cost_usd": audit["usage"]["total_cost_usd"],
            "unknown_cost_outcomes": audit["usage"]["unknown_cost_outcomes"],
        },
        cases=tuple(sorted(cases, key=lambda item: item.case_id)),
        demo_presets=_demo_presets(),
        graph_contract_disclosure=(
            "Graph contract v2 is displayed as built: FINDING -> CITES -> DOSSIER_EVIDENCE, "
            "FINDING -> ABOUT -> KEYWORD, and DOSSIER_EVIDENCE -> OBSERVES -> KEYWORD. "
            "The planned discriminated evidence union was replaced by a single "
            "DOSSIER_EVIDENCE occurrence node type plus evidence_kind."
        ),
        correction_ledger_path=(
            "data/presentation/m4/"
            f"{SNAPSHOT_VERSION}/presentation-corrections.md"
        ),
    )
    return snapshot.model_copy(update={"snapshot_sha256": compute_snapshot_sha256(snapshot)})


def publish_snapshot() -> Path:
    if SNAPSHOT_PATH.exists():
        raise FileExistsError(f"snapshot version already exists: {SNAPSHOT_PATH.parent}")
    snapshot = build_snapshot()
    with tempfile.TemporaryDirectory(prefix="regbridge-m4-snapshot-") as tmp:
        temporary_root = Path(tmp) / SNAPSHOT_VERSION
        temporary_root.mkdir(parents=True)
        (temporary_root / "snapshot.json").write_text(
            _canonical_json(snapshot.model_dump(mode="json")),
            encoding="utf-8",
            newline="\n",
        )
        (temporary_root / "presentation-corrections.md").write_text(
            "# M4 Presentation Correction Ledger\n\n"
            "No presentation-only corrections have been recorded for this snapshot.\n",
            encoding="utf-8",
            newline="\n",
        )
        target_root = SNAPSHOT_PATH.parent
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_root), str(target_root))
        _restore_inherited_acl(target_root)
    return SNAPSHOT_PATH


def _restore_inherited_acl(path: Path) -> None:
    """Keep sandbox-created Windows snapshots readable by normal local processes."""
    if os.name != "nt":
        return
    subprocess.run(
        ["icacls", str(path), "/inheritance:e", "/T", "/C"],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    path = publish_snapshot()
    print(path)


if __name__ == "__main__":
    main()
