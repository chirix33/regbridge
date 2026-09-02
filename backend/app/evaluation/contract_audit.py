"""Network-free contract audit. Only the isolated development bundle and named live run."""

import hashlib
import json
from typing import Any

from app.analyzer.prompts import SEMANTIC_INSPECTION_TASK
from app.baselines.direct import prepare_case, serialize_direct_request
from app.config import REPOSITORY_ROOT
from app.domain.enums import Decision, Severity
from app.domain.vocabulary import ACTION_CODES, output_vocabulary
from app.evaluation.live_configuration import configuration_material, content_digest
from app.evaluation.live_phase1 import LIVE_CONFIGURATION_ID, _atomic_write
from app.evaluation.metrics import MetricsScope, score_system
from app.evaluation.models import DirectDecisionOutput, RetrievalTrace, SystemPrediction
from app.evaluation.phase1_bundle import load_phase1_bundle, phase1_bundle_sha256
from app.llm.models import ModelRequest, SemanticFinding
from app.llm.responses import SYSTEM_INSTRUCTIONS, _strict_json_schema
from app.llm.serialization import CASE_PATTERN, UUID_PATTERN, serialize_semantic_request
from app.standards.evidence import EvidenceRegistry

PREVIOUS_RUN = REPOSITORY_ROOT / "results/live/m3-live-phase1-20260831T175309816872Z"
AUDIT_ROOT = REPOSITORY_ROOT / "results/live/contract-v2-review"


def _leaks(serialized: str, forbidden: tuple[str, ...]) -> bool:
    return bool(UUID_PATTERN.search(serialized) or CASE_PATTERN.search(serialized) or any(
        item and item.casefold() in serialized.casefold() for item in forbidden
    ))


def generate_audit() -> dict[str, Any]:
    bundle = load_phase1_bundle()
    old_rows = [json.loads(line) for line in (PREVIOUS_RUN / "predictions.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()]
    old_manifest = json.loads((PREVIOUS_RUN / "manifest.json").read_text(encoding="utf-8"))
    old_metrics = json.loads((PREVIOUS_RUN / "metrics.json").read_text(encoding="utf-8"))
    old_traces = tuple(RetrievalTrace.model_validate_json(line) for line in (
        PREVIOUS_RUN / "retrieval.jsonl"
    ).read_text(encoding="utf-8").splitlines())
    allowed_ids = {case.case_id for case in bundle.cases}
    if any(row["case_id"] not in allowed_ids for row in old_rows):
        raise ValueError("Historical audit rejected an outcome outside the train/dev allowlist")
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    direct_after = semantic_before = semantic_after = 0
    input_sizes = []
    for case_input in bundle.case_inputs:
        prepared = prepare_case(case_input)
        serialized = serialize_direct_request(prepared, evidence)
        forbidden = (case_input.case_id, case_input.fixture_id, case_input.selected_leaf_id)
        direct_after += _leaks(serialized, forbidden)
        input_sizes.append(len(SYSTEM_INSTRUCTIONS + serialized + json.dumps(
            _strict_json_schema(DirectDecisionOutput.model_json_schema()), sort_keys=True
        )))
        # Identical evidence to the isolated bundle, without executing/scoring RegBridge.
        request = ModelRequest(
            fixture_lookup_key=case_input.fixture_id, task=SEMANTIC_INSPECTION_TASK,
            context={"authority": "FDA", "center": "CDER", "target_standard": "eCTD-4.0"},
            evidence=case_input.dossier_evidence, prompt_template_version="1.0.0",
        )
        old = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        semantic_before += _leaks(old, forbidden)
        semantic_after += _leaks(serialize_semantic_request(request).serialized, forbidden)
    # Old B1 queries are the exact shared B0/B1 case serialization saved before changes.
    direct_before = sum(_leaks(trace.query, ()) for trace in old_traces)
    direct_rows = [row for row in old_rows if row["system"] in {"B0", "B1"}]
    noncanonical = sum(row["prediction"]["action"] not in ACTION_CODES for row in direct_rows)
    old_schema = old_manifest["configuration_material"]["direct_schema"]
    old_semantic_schema = old_manifest["configuration_material"]["semantic_schema"]
    old_severities = old_semantic_schema["$defs"]["Severity"]["enum"]
    new_severities = SemanticFinding.model_json_schema()["properties"]["severity"]["enum"]
    uuid = "78763013-836c-4015-bbb1-80dd2471b959"
    uuid_row = next(row for row in direct_rows if uuid in row["prediction"]["action"])
    uuid_trace = next(trace for trace in old_traces if trace.case_id == uuid_row["case_id"])
    old_packet = json.dumps({
        "task": old_manifest["configuration_material"]["direct_prompt"],
        "case_material": json.loads(uuid_trace.query),
        "evidence": [{"id": item.id, "source_sha256": item.source_sha256,
                      "locator": item.locator, "text": item.text}
                     for item in evidence
                     if item.id in {hit.evidence_id for hit in uuid_trace.hits}],
        "output_schema": "DirectDecisionOutput-v1",
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    reconstructed_digest = hashlib.sha256(old_packet.encode()).hexdigest()
    if reconstructed_digest != uuid_row["attempts"][0]["request_digest"]:
        raise ValueError("UUID provenance audit could not reconstruct the historical request")
    report: dict[str, Any] = {
        "audit_type": "network_free_contract_defect_validation_not_model_evaluation",
        "previous_run": PREVIOUS_RUN.name,
        "configuration_id": LIVE_CONFIGURATION_ID,
        "state": "awaiting_author_01_action_vocabulary_approval",
        "eligible_for_performance_claims": False,
        "current_fda_operational_availability": "not_operational", "expert_validated": False,
        "bundle_sha256": phase1_bundle_sha256(),
        "defect_counts": {
            "forbidden_semantic_severities_permitted_by_wire_schema": {
                "before": len(set(old_severities) & {"blocking", "unresolved"}),
                "after": len(set(new_severities) & {"blocking", "unresolved"}),
                "basis": "exhaustive schema enum inspection, not live output counts",
            },
            "direct_action_fields_without_canonical_enum": {
                "before": int("enum" not in old_schema["properties"]["action"]) * 2,
                "after": int("enum" not in DirectDecisionOutput.model_json_schema()[
                    "properties"]["action"]) * 2,
            },
            "historical_noncanonical_direct_actions": {
                "before": noncanonical, "denominator": len(direct_rows),
                "after_live": None, "reason": "rerun requires vocabulary approval",
            },
            "semantic_packets_with_identifier_leakage": {
                "before": semantic_before, "after": semantic_after, "denominator": 18,
                "basis": "serialize same isolated evidence under old/new serializer; no inference",
            },
            "direct_packets_with_identifier_leakage": {
                "before": direct_before, "after": direct_after, "denominator": 18,
                "basis": "old saved shared case queries; new full B0 packets",
            },
        },
        "uuid_provenance": {
            "input_digest_matches_saved_attempt": True,
            "request_digest": reconstructed_digest,
            "in_input": uuid in old_packet,
            "in_schema": uuid in json.dumps(old_schema),
            "in_instructions": (
                uuid in old_manifest["configuration_material"]["system_instructions"]
            ),
            "in_raw_model_output": uuid in uuid_row["attempts"][0]["final_json_text"],
            "conclusion": (
                "unsupported model-generated identifier; not demonstrated internal copying"
            ),
        },
        "maximum_new_b0_model_facing_characters": max(input_sizes),
        "historical_failed_semantic_attempts": sum(
            attempt["cause"] == "schema_validation" for row in old_rows
            for attempt in row["attempts"] if row["system"] == "RegBridge"
        ),
        "regbridge_metrics": None,
        "regbridge_metrics_reason": "withheld until all 18 outcomes complete; no comparison",
        "phase2_cap": None, "phase2_enabled": False, "frozen_prompt_digest": None,
        "after_live_metrics": None,
        "after_live_metrics_reason": "No rerun authorized before proposed vocabulary approval",
        "acceptance_criterion": (
            "named contract defects cease; no accuracy/F1 improvement criterion"
        ),
        "baseline_metric_audit": [],
    }
    for system in ("B0", "B1"):
        # Historical records were valid under v1. Do not relabel them or pretend they pass v2.
        predictions = []
        for row in direct_rows:
            if row["system"] == system:
                raw = {**row["prediction"]}
                raw["decision"] = Decision(raw["decision"])
                raw["severity"] = Severity(raw["severity"])
                predictions.append(SystemPrediction.model_construct(**raw))
        scoped_splits: tuple[tuple[str | None, MetricsScope], ...] = (
            ("train", "phase1-train"), ("development", "phase1-development"),
            (None, "phase1-train-development"),
        )
        for split, scope in scoped_splits:
            cases = tuple(case for case in bundle.cases if split is None or case.split == split)
            ids = {case.case_id for case in cases}
            rescored, _ = score_system(
                cases=cases, predictions=tuple(p for p in predictions if p.case_id in ids),
                retrieval_traces=old_traces, scope=scope, seed=20270829,
                regulatory_evidence_ids=frozenset(item.id for item in evidence),
            )
            before = next(item for item in old_metrics["reports"]
                          if item["system"] == system and item["scope"] == scope)
            report["baseline_metric_audit"].append({
                "system": system, "scope": scope,
                "result_status": "historical defective-contract diagnostics; not a comparison",
                "before_accuracy": before["accuracy"], "before_macro_f1": before["macro_f1"],
                "same_saved_predictions_rescored_accuracy": rescored.accuracy,
                "same_saved_predictions_rescored_macro_f1": rescored.macro_f1,
                "unsafe_fnr": rescored.unsafe_false_negative_rate.model_dump(mode="json"),
                "review_bypass": rescored.review_bypass_rate.model_dump(mode="json"),
                "vocabulary_diagnostic": rescored.vocabulary_diagnostic.model_dump(mode="json"),
                "after_new_inference_accuracy": None, "after_new_inference_macro_f1": None,
            })
    configuration = configuration_material()
    report["new_configuration_sha256"] = content_digest(configuration)
    _atomic_write(
        AUDIT_ROOT / "defect-audit.json", json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    _atomic_write(AUDIT_ROOT / "development-configuration.json", json.dumps({
        "configuration_id": LIVE_CONFIGURATION_ID,
        "status": "declared_pending_author_01_action_vocabulary_approval_not_executed",
        "configuration_sha256": content_digest(configuration),
        "action_vocabulary_sha256": content_digest(output_vocabulary()),
        "configuration_material": configuration,
        "phase2_enabled": False, "frozen_prompt_digest": None,
        "current_fda_operational_availability": "not_operational", "expert_validated": False,
    }, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    report = generate_audit()
    print(json.dumps({
        "state": report["state"], "defect_counts": report["defect_counts"],
        "configuration_sha256": report["new_configuration_sha256"],
        "maximum_b0_characters": report["maximum_new_b0_model_facing_characters"],
        "baseline_metric_audit": report["baseline_metric_audit"],
    }, indent=2))


if __name__ == "__main__":
    main()
