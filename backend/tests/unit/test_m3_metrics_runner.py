import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from app.evaluation import runner
from app.evaluation.metrics import wilson_interval
from app.evaluation.runner import CONFIGURATION_ID, run_evaluation


def test_wilson_interval_matches_held_out_zero_miss_boundary() -> None:
    low, high = wilson_interval(0, 8)
    assert low == 0
    assert high is not None
    assert round(high, 6) == 0.324408


def test_deterministic_evaluation_reproduces_prediction_and_metric_content() -> None:
    first = run_evaluation(CONFIGURATION_ID)
    manifest_path = runner.RESULT_DIRECTORY / "manifest.json"
    first_manifest = manifest_path.read_bytes()
    build_manifest = runner.RESULT_DIRECTORY / "graph-benchmark-build-manifest.json"
    assert build_manifest.read_bytes() == first_manifest
    manifest = json.loads(first_manifest)
    assert manifest["graph_benchmark_build"]["graph_schema_version"] == "2.0.0"
    assert manifest["graph_benchmark_build"]["frozen_material"] == {
        "benchmark_sha256": "9b1e94fd0709cbbe8573e6882687b931d88c1da775932f0cbaf9dd55eca6fc75",
        "fixture_validation_v1_rewritten": False,
        "labels_families_splits_changed": False,
    }
    assert manifest["graph_benchmark_build"]["model_facing_contract"][
        "request_local_aliasing_retained"
    ] is True
    second = run_evaluation(CONFIGURATION_ID)
    assert first_manifest == manifest_path.read_bytes()
    assert first.state == "completed"
    assert first.run_type == "deterministic_fixture_validation"
    assert first.empirical_model_run is False
    assert first.eligible_for_performance_claims is False
    assert first.artifacts is not None
    assert second.artifacts is not None
    assert first.artifacts.prediction_content_sha256 == second.artifacts.prediction_content_sha256
    assert first.artifacts.metrics_content_sha256 == second.artifacts.metrics_content_sha256
    assert len(first.cases) == 120
    assert len(first.metrics) == 8
    b2 = next(
        item for item in first.metrics if item.system == "B2" and item.scope == "held-out-test"
    )
    assert b2.unsafe_false_negative_rate.numerator == 2
    assert b2.unsafe_false_negative_rate.denominator == 8
    assert b2.review_bypass_rate.numerator == 2
    assert b2.families_with_unsafe_misses == 1
    assert b2.action_required_family_count == 3
    assert b2.inference_claims == "exploratory-only-no-independence-or-significance-claims"
    for report in first.metrics:
        if report.scope == "held-out-test":
            assert len(report.family_sensitivity) == 6
            assert sum(item.eligible_cases for item in report.family_sensitivity) == 8
            assert sum(item.eligible_cases == 0 for item in report.family_sensitivity) == 3


def test_source_digest_ignores_generated_outputs_caches_and_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "REPOSITORY_ROOT", tmp_path)
    source = tmp_path / "implementation.py"
    source.write_text("source-v1", encoding="utf-8")
    before = runner._tree_digest()
    for relative in (
        ".mypy_cache/cache.json", ".ruff_cache/cache.json", "frontend/dist/index.html",
        "frontend/tsconfig.app.tsbuildinfo", "results/run.json", ".env",
        "paper/tables/validation/table.csv", "runtime.sqlite3",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated-or-secret", encoding="utf-8")
    assert runner._tree_digest() == before
    source.write_text("source-v2", encoding="utf-8")
    assert runner._tree_digest() != before


def test_manifest_and_exports_are_physically_separated() -> None:
    run = run_evaluation(CONFIGURATION_ID)
    assert run.artifacts is not None
    root = Path(__file__).resolve().parents[3]
    manifest = root / run.artifacts.manifest_json
    paper = root / run.artifacts.paper_table_csv
    assert "results/validation" in manifest.as_posix()
    assert "paper/tables/validation" in paper.as_posix()
    assert manifest.is_file()
    assert paper.is_file()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["current_fda_operational_availability"] == "not_operational"
    predictions = root / run.artifacts.predictions_jsonl
    metrics = root / run.artifacts.metrics_json
    assert hashlib.sha256(predictions.read_bytes()).hexdigest() == (
        run.artifacts.prediction_content_sha256
    )
    assert hashlib.sha256(metrics.read_bytes()).hexdigest() == (
        run.artifacts.metrics_content_sha256
    )


def test_presentation_separates_fixtures_deterministic_and_retrieval_results() -> None:
    run = run_evaluation(CONFIGURATION_ID)
    assert run.artifacts is not None
    root = Path(__file__).resolve().parents[3]
    summary = (root / run.artifacts.summary_markdown).read_text(encoding="utf-8")
    assert "| System | Result status |" in summary
    assert "B2 unsafe misses occurred in 1 of the 3 held-out families" in summary
    assert "no statistical interpretation" in summary
    assert "Measured B1 BM25 retrieval" in summary
    headline = tuple(item for item in run.metrics if item.scope == "held-out-test")
    rows = list(csv.DictReader(io.StringIO(runner._metrics_csv(headline))))
    for row, report in zip(rows, headline, strict=True):
        if report.system == "B2":
            assert row["result_status"] == "genuine deterministic experimental output"
            assert row["unsafe_fn_wilson_low"]
        else:
            assert row["result_status"] == "fixture validation only"
            assert row["unsafe_fn_wilson_low"] == row["unsafe_fn_wilson_high"] == ""
            assert report.unsafe_false_negative_rate.wilson_95_high is not None
            assert report.interval_interpretation == (
                "scorer validation only; no statistical interpretation"
            )
            score_row = next(line for line in summary.splitlines() if line.startswith(
                f"| {report.system} | fixture validation only | 0.000 ("
            ))
            assert "not interpreted" in score_row

    b2_path = root / run.artifacts.paper_deterministic_table_csv
    b2_rows = list(csv.DictReader(io.StringIO(b2_path.read_text(encoding="utf-8"))))
    assert "/deterministic/" in b2_path.as_posix()
    assert [row["system"] for row in b2_rows] == ["B2"]
    assert b2_rows[0]["families_with_unsafe_misses"] == "1"
    assert b2_rows[0]["action_required_family_count"] == "3"

    retrieval_path = root / run.artifacts.paper_retrieval_table_csv
    retrieval_rows = list(csv.DictReader(io.StringIO(retrieval_path.read_text(encoding="utf-8"))))
    assert "/retrieval/" in retrieval_path.as_posix()
    assert len(retrieval_rows) == 1
    measured = next(item.retrieval for item in headline if item.system == "B1")
    assert measured is not None
    assert retrieval_rows[0]["result_status"] == "genuine deterministic retrieval measurement"
    assert int(retrieval_rows[0]["evaluated_cases"]) == measured.evaluated_cases
    for key in ("recall_at_3", "precision_at_3", "mrr"):
        assert float(retrieval_rows[0][key]) == getattr(measured, key)
    assert "accuracy" not in retrieval_rows[0]
    assert "macro_f1" not in retrieval_rows[0]
