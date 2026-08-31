"""Network-free probes on synthetic requests and the isolated train/development bundle only."""

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.baselines.direct import prepare_case, serialize_direct_request
from app.baselines.retrieval import BM25Retriever
from app.config import REPOSITORY_ROOT
from app.domain.vocabulary import ACTION_CODES, ACTION_DEFINITIONS, output_vocabulary
from app.evaluation import live_configuration as config
from app.evaluation import live_phase1 as live
from app.evaluation import phase1_b2 as b2
from app.evaluation.phase1_bundle import load_phase1_bundle
from app.llm.models import ModelRequest, SemanticRiskOutput
from app.llm.responses import SYSTEM_INSTRUCTIONS, _strict_json_schema
from app.llm.serialization import serialize_semantic_request
from app.parsers.ectd322 import FixtureCatalog
from app.standards.evidence import EvidenceRegistry


def test_identical_neutral_defined_packet_and_documentation_for_all_four_systems() -> None:
    packet = output_vocabulary()
    assert len(ACTION_CODES) == len(ACTION_DEFINITIONS) == 11
    assert list(ACTION_CODES) == sorted(ACTION_CODES)
    assert list(packet["action_definitions"]) == list(ACTION_CODES)
    document = (REPOSITORY_ROOT / "docs/evaluation/M3-ACTION-DEFINITIONS-REVIEW.md").read_text()
    for code, definition in packet["action_definitions"].items():
        assert definition and "\n" not in definition
        assert f"| `{code}` | {definition} |" in document
        assert not re.search(r"\b(when|if|because|applies|A\d{3}|B\d{3}|C\d{3})\b", definition)
        assert not re.search(r"\d+\.\d+\.[A-Z]", definition)
        assert all(decision not in definition for decision in packet["decisions"])
    assert len(set(packet["action_definitions"].values())) == 11
    evidence = tuple(EvidenceRegistry().load())
    case_input = load_phase1_bundle().case_inputs[0]
    prepared = prepare_case(case_input)
    b0_packet, b1_packet = (
        json.loads(serialize_direct_request(prepared, spans))
        for spans in (evidence, evidence[:3])
    )
    semantic = serialize_semantic_request(ModelRequest(
        fixture_lookup_key="synthetic", task="Inspect evidence.", context={},
        evidence=case_input.dossier_evidence, prompt_template_version="1.0.0",
    ))
    assert b0_packet["output_vocabulary"] == b1_packet["output_vocabulary"] == (
        json.loads(semantic.serialized)["output_vocabulary"]
    ) == b2.scoring_contract()["output_vocabulary"] == packet
    assert b0_packet["case_material"] == b1_packet["case_material"]
    assert "action_definitions" not in prepared.serialized  # Not part of BM25 query.


def test_real_definition_edit_invalidates_configuration_and_heldout_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = config.configuration_material()
    gate = config.HeldOutApprovalGate(
        "author-01", config.content_digest(config.template_digests(original)),
        config.content_digest(original), 25000,
    )
    monkeypatch.setitem(ACTION_DEFINITIONS, ACTION_CODES[0], "Synthetic changed definition.")
    edited = config.configuration_material()
    assert config.content_digest(edited) != config.content_digest(original)
    assert config.template_digests(edited) != config.template_digests(original)
    for guard in (gate.before_loading, gate.before_repetition, gate.before_dispatch):
        with pytest.raises(ValueError, match="configuration digest mismatch"):
            guard(lambda: pytest.fail("must fail before any held-out operation"))


def test_definition_packet_never_truncates_and_keeps_fixed_evidence_order() -> None:
    evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    retriever = BM25Retriever(evidence)
    schema = _strict_json_schema(live.DirectDecisionOutput.model_json_schema())
    schema_characters = len(json.dumps(schema, sort_keys=True))
    for case in load_phase1_bundle().case_inputs:
        prepared = prepare_case(case)
        trace = retriever.retrieve(case_id=case.case_id, query=prepared.serialized)
        ids = {item.evidence_id for item in trace.hits}
        for selected in (evidence, tuple(item for item in evidence if item.id in ids)):
            serialized = serialize_direct_request(prepared, tuple(reversed(selected)))
            assert len(SYSTEM_INSTRUCTIONS) + len(serialized) + schema_characters <= 16000
            assert json.loads(serialized)["evidence"] == [
                {"id": item.id, "source_sha256": item.source_sha256,
                 "locator": item.locator, "text": item.text} for item in selected
            ]


@pytest.mark.asyncio
async def test_b2_fresh_rescore_and_comparison_guard_without_network_or_full_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Isolated B2 must not access a network client, combined benchmark, or catalog")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(FixtureCatalog, "__init__", forbidden)
    monkeypatch.setattr("app.evaluation.phase1_bundle.load_frozen_benchmark", forbidden)
    semantic_packets: list[dict[str, Any]] = []
    omitted = b2.OmittedSemanticModel.complete

    async def inspect_omitted_request(self: Any, request: ModelRequest, output_type: Any) -> Any:
        serialized = serialize_semantic_request(request).serialized
        semantic_packets.append(json.loads(serialized))
        schema = _strict_json_schema(SemanticRiskOutput.model_json_schema())
        assert len(SYSTEM_INSTRUCTIONS + serialized + json.dumps(schema, sort_keys=True)) <= 16000
        return await omitted(self, request, output_type)

    monkeypatch.setattr(b2.OmittedSemanticModel, "complete", inspect_omitted_request)
    bundle = load_phase1_bundle()
    result = await b2.rescore_b2(bundle, seed=20270829)
    assert semantic_packets
    assert all(item["output_vocabulary"] == output_vocabulary() for item in semantic_packets)
    assert len(result.predictions) == 18
    assert {item.scope for item in result.reports} == {
        "phase1-train", "phase1-development", "phase1-train-development",
    }
    assert all(item.requests == item.input_tokens == item.output_tokens == 0
               and not item.empirical_model_observation for item in result.predictions)
    assert result.contract["output_vocabulary"] == output_vocabulary()
    with pytest.raises(ValueError, match="coverage"):
        replace(result, predictions=result.predictions[:-1]).validate_for_comparison(bundle)
    with pytest.raises(ValueError, match="configuration digest mismatch"):
        replace(result, configuration_sha256="0" * 64).validate_for_comparison(bundle)
    with pytest.raises(ValueError, match="scoring contract mismatch"):
        replace(result, contract={}).validate_for_comparison(bundle)

    # A synthetic comparison checks reporting only; none of these are live observations.
    monkeypatch.setattr(live, "LIVE_RESULTS_ROOT", tmp_path / "results/live")
    monkeypatch.setattr(live, "LIVE_PAPER_ROOT", tmp_path / "paper/tables/live")
    retriever = BM25Retriever(tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id)))
    traces = {item.case_id: retriever.retrieve(
        case_id=item.case_id, query=prepare_case(item).serialized,
    ) for item in bundle.case_inputs}
    outcomes = tuple(live.LiveOutcome(
        system, pred.case_id, case.split, "valid_prediction",
        pred.model_copy(update={"system": system}),
        traces[pred.case_id] if system == "B1" else None, (), (), None,
    ) for system in live.LIVE_SYSTEMS
        for pred, case in zip(result.predictions, bundle.cases, strict=True))
    path = live._write_artifacts(
        bundle=bundle, tokenizer_name="synthetic", outcomes=outcomes,
        stopped_reason=None, run_id="synthetic-defined-actions", b2_rescore=result,
    )
    manifest = json.loads((path / "manifest.json").read_text())
    artifact = json.loads((path / "b2-contract-rescore.json").read_text())
    assert manifest["cross_system_comparison_status"] == "complete_development_only"
    assert manifest["b2_rescore"]["configuration_sha256"] == (
        manifest["digests"]["configuration_sha256"]
    ) == artifact["configuration_sha256"]
    assert artifact["scoring_contract"]["output_vocabulary"] == output_vocabulary()
    assert artifact["eligible_for_performance_claims"] is False
    assert artifact["result_status"] == b2.B2_RESULT_STATUS
    assert "B2 | phase1-train-development | genuine deterministic" in (
        path / "summary.md"
    ).read_text()
    assert manifest["configuration_material"]["action_vocabulary_disclosure"][
        "b0_b1_receive_taxonomy_in_input"
    ] is True
    with pytest.raises(ValueError, match="requires a fresh B2"):
        live._write_artifacts(
            bundle=bundle, tokenizer_name="synthetic", outcomes=outcomes,
            stopped_reason=None, run_id="synthetic-missing-b2",
        )
    assert not (tmp_path / "results/live/synthetic-missing-b2/summary.md").exists()


@pytest.mark.asyncio
async def test_b2_rejects_disallowed_split_before_prediction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = load_phase1_bundle()
    tampered = bundle.model_copy(update={"cases": (
        bundle.cases[0].model_copy(update={"split": "test"}), *bundle.cases[1:],
    )})

    async def forbidden(*args: Any) -> Any:
        pytest.fail("No fixture preparation may precede the membership guard")

    monkeypatch.setattr(b2, "_predict", forbidden)
    with pytest.raises(ValueError, match="disallowed split"):
        await b2.rescore_b2(tampered, seed=1)
