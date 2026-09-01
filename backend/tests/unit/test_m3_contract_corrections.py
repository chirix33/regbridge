import ast
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import yaml
from app.baselines.direct import prepare_case, serialize_direct_request
from app.config import REPOSITORY_ROOT
from app.domain.enums import Decision, Severity
from app.domain.models import AnalysisResult, DossierEvidence, RepairAction
from app.domain.vocabulary import ACTION_CODES, output_vocabulary
from app.evaluation import live_configuration as live_config
from app.evaluation import live_phase1 as live
from app.evaluation.live_configuration import require_development_approval
from app.evaluation.metrics import REPRESENTED_CLASSES, score_system
from app.evaluation.models import DirectDecisionOutput, SystemName, SystemPrediction
from app.evaluation.phase1_bundle import load_phase1_bundle
from app.llm.models import ModelRequest, SemanticFinding, SemanticRiskOutput
from app.llm.responses import ResponsesStructuredModel
from app.llm.serialization import serialize_semantic_request
from app.standards.evidence import EvidenceRegistry
from pydantic import ValidationError


def test_shared_action_enum_exactly_matches_existing_code_and_rule_repairs() -> None:
    tree = ast.parse((REPOSITORY_ROOT / "backend/app/analyzer/service.py").read_text())
    codes = {
        keyword.value.value for call in ast.walk(tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        and call.func.id == "RepairAction" for keyword in call.keywords
        if keyword.arg == "type" and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }
    for filename in ("heading-rules.yaml", "metadata-rules.yaml"):
        rules = yaml.safe_load((REPOSITORY_ROOT / "data/rules" / filename).read_text())
        codes.update(rule["repair_type"] for rule in rules["rules"] if rule.get("repair_type"))
    assert set(ACTION_CODES) == codes
    for model, field in ((DirectDecisionOutput, "action"), (SystemPrediction, "action"),
                         (RepairAction, "type")):
        schema = model.model_json_schema()["properties"][field]
        assert set(schema["enum"]) == codes
        assert "pattern" not in schema


def test_six_decisions_are_identical_for_every_system_output_schema() -> None:
    for model in (DirectDecisionOutput, SystemPrediction, AnalysisResult):
        assert set(model.model_json_schema()["$defs"]["Decision"]["enum"]) == {
            item.value for item in Decision
        }
    assert len(output_vocabulary()["decisions"]) == 6


def test_semantic_schema_matches_validator_without_relaxing_second_boundary() -> None:
    assert SemanticFinding.model_json_schema()["properties"]["severity"]["enum"] == [
        "informational", "low", "medium", "high",
    ]
    forged = SemanticFinding.model_construct(
        id="synthetic-finding", basis="observation", summary="Synthetic",
        severity=Severity.UNRESOLVED, evidence_ids=("supplied-001",),
        category="ambiguous_reference",
    )
    with pytest.raises(ValidationError, match="may not claim blocking or unresolved"):
        SemanticRiskOutput(
            fixture_version="1.0.0", abstained=False, abstain_reason=None,
            findings=(forged,), confidence=0.5,
        )


def test_unresolved_severity_is_intended_only_in_direct_decision_contract() -> None:
    direct = DirectDecisionOutput.model_validate({
        "decision": "HUMAN_REGULATORY_REVIEW",
        "severity": "unresolved",
        "action": "HUMAN_VERIFY_STALE_CONTENT",
        "human_review_required": True,
        "rationale": "The direct agent cannot resolve the supplied evidence.",
        "evidence_ids": [],
    })
    assert direct.severity == Severity.UNRESOLVED
    with pytest.raises(ValidationError):
        SemanticFinding.model_validate({
            "id": "finding-001",
            "basis": "inference",
            "summary": "Unresolved is forbidden for a semantic signal.",
            "severity": "unresolved",
            "evidence_ids": ["case-evidence-001"],
        })


@pytest.mark.parametrize("action", [
    "Doage-making.uispendedlyolinking", "Do_gnot_resubmit_gthe",
    "Createousealvidenceary_access_safety.allergy.v1.0.0-beta5",
    "78763013-836c-4015-bbb1-80dd2471b959",
])
def test_identifier_shaped_prose_and_uuids_are_not_accepted_actions(action: str) -> None:
    with pytest.raises(ValidationError):
        DirectDecisionOutput.model_validate({
            "decision": "HUMAN_REGULATORY_REVIEW", "severity": "unresolved", "action": action,
            "human_review_required": True, "rationale": "Synthetic", "evidence_ids": [],
        })


def synthetic_request() -> ModelRequest:
    evidence = DossierEvidence(
        id="leaf-a901-selected-text", artifact_id="artifact-secret-fixture-a901",
        kind="text", locator="secret-fixture-a901/documents/a901.pdf#page1",
        text="Historical heading 3.2.S.1.2 is not current. UUID "
             "78763013-836c-4015-bbb1-80dd2471b959; see leaf-a901-selected-text.",
        file_sha256="0" * 64,
    )
    return ModelRequest(
        fixture_lookup_key="secret-fixture-a901", task="Inspect supplied evidence.",
        context={"identifier": "78763013-836c-4015-bbb1-80dd2471b959"},
        evidence=(evidence,), prompt_template_version="1.0.0",
    )


def test_aliases_remove_embedded_ids_and_locators_preserving_ctd_and_text_semantics() -> None:
    request = synthetic_request()
    serialized = serialize_semantic_request(request).serialized
    for forbidden in ("a901", "secret-fixture", "leaf-a901", "documents/a901.pdf", "78763013"):
        assert forbidden not in serialized.casefold()
    assert "Historical heading 3.2.S.1.2 is not current." in serialized
    assert json.loads(serialized)["output_vocabulary"] == output_vocabulary()
    assert serialize_semantic_request(request).serialized == serialized
    assert request.evidence[0].id == "leaf-a901-selected-text"  # Source never changed.

    case = load_phase1_bundle().case_inputs[0]
    material = {**case.material, "selected_leaf": {**case.material["selected_leaf"],
        "title": "A901 secret-fixture-a901 78763013-836c-4015-bbb1-80dd2471b959"}}
    case = case.model_copy(update={
        "case_id": "A901", "fixture_id": "secret-fixture-a901", "material": material,
        "dossier_evidence": request.evidence,
    })
    prepared = prepare_case(case)
    assert all(value not in prepared.serialized.casefold() for value in (
        "a901", "secret-fixture", "78763013", "documents/a901.pdf",
    ))
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    b0, b1 = (json.loads(serialize_direct_request(prepared, items))
              for items in (evidence, evidence[:3]))
    assert b0["case_material"] == b1["case_material"]
    assert b0["output_vocabulary"] == b1["output_vocabulary"] == output_vocabulary()


@pytest.mark.asyncio
async def test_semantic_wire_aliases_translate_back_only_after_validation() -> None:
    request = synthetic_request()

    def handler(wire: httpx.Request) -> httpx.Response:
        packet = json.loads(json.loads(wire.content)["input"])
        assert "a901" not in json.dumps(packet).casefold()
        return httpx.Response(200, json={"status": "completed", "output_text": json.dumps({
            "fixture_version": "1.0.0", "abstained": False, "abstain_reason": None,
            "findings": [{"id": "finding-001", "basis": "observation", "summary": "Historical",
                          "severity": "low", "category": "benign_historical_reference",
                          "evidence_ids": [packet["evidence"][0]["id"]]}], "confidence": 0.5,
        })})

    model = ResponsesStructuredModel(
        base_url="https://example.invalid", api_key="test", model="gpt-5.5", timeout_seconds=1,
        count_final_tokens=lambda _: 100, transport=httpx.MockTransport(handler),
    )
    completion = await model.complete(request, SemanticRiskOutput)
    assert completion.output.findings[0].evidence_ids == (request.evidence[0].id,)
    assert "a901" not in cast(str, model.last_attempts[0].final_json_text)


@pytest.mark.parametrize("system", ["B0", "B1", "B2", "RegBridge"])
def test_option_a_outside_class_scoring_is_identical_for_all_systems(system: SystemName) -> None:
    template = load_phase1_bundle().cases[0]
    cases = tuple(template.model_copy(update={
        "case_id": f"synthetic-{i}",
        "reference": template.reference.model_copy(update={"decision": label}),
    }) for i, label in enumerate(REPRESENTED_CLASSES))
    predicted = (Decision.DO_NOT_REUSE, *REPRESENTED_CLASSES[1:])
    predictions = tuple(SystemPrediction(
        system=system, case_id=case.case_id, decision=label, severity=Severity.LOW,
        action="NO_MATERIAL_REPAIR", human_review_required=False, unconditional_reuse=False,
        rationale="Synthetic", prediction_source="contract_fixture", latency_ms=0, requests=0,
        input_tokens=0, output_tokens=0, cost_usd=None,
    ) for case, label in zip(cases, predicted, strict=True))
    report, _ = score_system(
        cases=cases, predictions=predictions, retrieval_traces=(), scope="phase1-train",
        seed=1, regulatory_evidence_ids=frozenset(),
    )
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.macro_f1 == pytest.approx(2 / 3)
    assert report.per_class[REPRESENTED_CLASSES[0].value].recall == 0
    assert report.per_class[REPRESENTED_CLASSES[1].value].precision == 1
    diagnostic = report.vocabulary_diagnostic
    assert diagnostic.outside_counts_by_decision["DO_NOT_REUSE"] == 1
    assert diagnostic.outside_represented_rate == pytest.approx(1 / 3)
    assert diagnostic.accuracy_excluding_outside_predictions == 1
    outside = tuple(item.model_copy(update={"decision": Decision.DO_NOT_REUSE})
                    for item in predictions)
    empty, _ = score_system(cases=cases, predictions=outside, retrieval_traces=(),
                           scope="phase1-train", seed=1, regulatory_evidence_ids=frozenset())
    assert empty.vocabulary_diagnostic.accuracy_excluding_outside_predictions is None
    assert empty.vocabulary_diagnostic.safety_caveat


@pytest.mark.asyncio
async def test_no_rerun_before_action_vocabulary_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden() -> Any:
        pytest.fail("Must reject before bundle or model access")

    monkeypatch.setattr(live, "load_phase1_bundle", forbidden)
    monkeypatch.setattr(live_config, "REPOSITORY_ROOT", tmp_path)
    with pytest.raises(ValueError, match="graph-contract-v2.*author-01"):
        require_development_approval()
    with pytest.raises(ValueError, match="graph-contract-v2.*author-01"):
        await live.run_phase1_live()


def test_partial_regbridge_metrics_are_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = load_phase1_bundle()
    case = bundle.cases[0]
    prediction = SystemPrediction(
        system="RegBridge", case_id=case.case_id, decision=Decision.HUMAN_REGULATORY_REVIEW,
        severity=Severity.UNRESOLVED, action="HUMAN_VERIFY_STALE_CONTENT",
        human_review_required=True, unconditional_reuse=False, rationale="Synthetic",
        prediction_source="hybrid_contract_fixture", latency_ms=0, requests=0,
        input_tokens=0, output_tokens=0, cost_usd=None,
    )
    outcome = live.LiveOutcome(
        "RegBridge", case.case_id, case.split, "valid_prediction", prediction, None, (), (), None,
    )
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", tmp_path / "results/live")
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper/tables/live")
    path = live._write_artifacts(
        bundle=bundle, tokenizer_name="synthetic", outcomes=(outcome,), stopped_reason="test",
    )
    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["reports"] == []
    assert json.loads((path / "metrics.json").read_text())["reports"] == []
    assert manifest["regbridge_metrics_status"] == "withheld_until_all_18_outcomes_complete"
    assert manifest["cross_system_comparison_status"].startswith("prohibited")
    assert manifest["phase2_cap_proposal"]["status"] == "withheld"
