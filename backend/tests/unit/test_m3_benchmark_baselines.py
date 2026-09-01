import hashlib
import math
from pathlib import Path

import pytest
from app.baselines.direct import (
    DIRECT_INPUT_CHARACTER_LIMIT,
    PreparedCase,
    prepare_case,
    serialize_direct_request,
)
from app.baselines.retrieval import BM25Retriever, tokenize
from app.baselines.runner import BaselineRunner
from app.domain.enums import Decision
from app.evaluation.benchmark import (
    BenchmarkPromotionError,
    load_frozen_benchmark,
    promote_approved_ledger,
)
from app.evaluation.models import SystemName
from app.standards.evidence import EvidenceRegistry


def test_frozen_benchmark_matches_approved_distribution_and_governance() -> None:
    benchmark = load_frozen_benchmark()
    assert len(benchmark.cases) == 30
    assert benchmark.expert_validated is False
    assert benchmark.operational_availability == "not_operational"
    assert all(
        case.review_status.value == "author_adjudicated_for_demo" for case in benchmark.cases
    )
    assert all(case.review_event.reviewer_id == "author-01" for case in benchmark.cases)
    assert all(case.review_event.expert_validated is False for case in benchmark.cases)
    test = [case for case in benchmark.cases if case.split == "test"]
    assert len(test) == 12
    assert len({case.fixture_family for case in test}) == 6


def test_promotion_rejects_any_unapproved_ledger_digest() -> None:
    benchmark_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "benchmark"
        / "frozen"
        / "benchmark-v1.0.0.json"
    )
    before = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()
    with pytest.raises(BenchmarkPromotionError, match="digest does not match"):
        promote_approved_ledger(author_id="author-01", approved_ledger_sha256="0" * 64)
    assert hashlib.sha256(benchmark_path.read_bytes()).hexdigest() == before


def test_case_input_and_direct_serialization_exclude_reference_information() -> None:
    case = load_frozen_benchmark().cases[0]
    case_input = BaselineRunner().case_input(case)
    serialized_input = case_input.model_dump_json()
    assert "reference_decision" not in serialized_input
    assert "reference_severity" not in serialized_input
    assert "required_rule_ids" not in serialized_input
    assert "acceptable_evidence_ids" not in serialized_input
    prepared = prepare_case(case_input)
    request = serialize_direct_request(prepared, BaselineRunner().evidence)
    for forbidden in (
        case.case_id,
        case.fixture_id,
        case.selected_leaf_id,
        case.reference.rationale,
        *case.reference.required_rule_ids,
    ):
        assert forbidden not in request
    assert "acceptable_evidence_ids" not in request
    assert all(decision.value in request for decision in Decision)


def test_direct_input_fails_closed_above_character_limit() -> None:
    prepared = PreparedCase(
        material={"bounded_case_material": "x" * DIRECT_INPUT_CHARACTER_LIMIT},
        serialized="",
        alias_to_evidence_id={},
    )
    with pytest.raises(ValueError, match="silent truncation is forbidden"):
        serialize_direct_request(prepared, ())


def test_bm25_preserves_dotted_identifiers_and_breaks_ties_by_evidence_id() -> None:
    assert tokenize("Heading 3.2.S.1.2 REMAINS") == (
        "heading",
        "3.2.s.1.2",
        "remains",
    )
    corpus = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
    trace = BM25Retriever(corpus).retrieve(case_id="query-contract", query="qxzvplm")
    assert [hit.evidence_id for hit in trace.hits] == sorted(item.id for item in corpus)[:3]
    assert all(hit.score == 0 for hit in trace.hits)
    assert trace.k1 == 1.5
    assert trace.b == 0.75
    # Deliberate fullwidth text exercises the approved NFKC normalization.
    assert tokenize("３.２.Ｓ.１.２ Straße") == ("3.2.s.1.2", "strasse")  # noqa: RUF001


def test_bm25_formula_ranking_and_configuration_are_fixed() -> None:
    base = EvidenceRegistry().load()[0]
    corpus = tuple(
        base.model_copy(update={"id": identifier, "locator": "", "text": passage})
        for identifier, passage in (
            ("evidence-a", "alpha alpha"),
            ("evidence-b", "alpha beta"),
            ("evidence-c", "beta beta"),
        )
    )
    trace = BM25Retriever(corpus).retrieve(case_id="formula-probe", query="alpha")
    idf = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    assert [item.evidence_id for item in trace.hits] == [
        "evidence-a", "evidence-b", "evidence-c"
    ]
    assert trace.hits[0].score == pytest.approx(idf * (2 * 2.5) / (2 + 1.5))
    assert trace.hits[1].score == pytest.approx(idf)
    assert trace.hits[2].score == 0
    with pytest.raises(ValueError, match="configuration is frozen"):
        BM25Retriever(corpus, k1=2)


def test_b1_query_is_label_free_and_logs_fixed_hashes_and_scores() -> None:
    case = load_frozen_benchmark().cases[1]
    runner = BaselineRunner()
    _, trace = runner.run("B1", runner.case_input(case))
    assert trace is not None
    for forbidden in (
        case.case_id,
        case.fixture_id,
        case.reference.rationale,
        *case.reference.required_rule_ids,
        *case.reference.acceptable_evidence_ids,
    ):
        assert forbidden not in trace.query
    assert len(trace.corpus_sha256) == 64
    assert len(trace.configuration_sha256) == 64
    assert [hit.rank for hit in trace.hits] == [1, 2, 3]


def test_all_four_systems_share_one_runner_without_label_input() -> None:
    benchmark = load_frozen_benchmark()
    runner = BaselineRunner()
    case = next(item for item in benchmark.cases if item.archetype == "unavailable-heading")
    case_input = runner.case_input(case)
    systems: tuple[SystemName, ...] = ("B0", "B1", "B2", "RegBridge")
    outputs = {system: runner.run(system, case_input)[0] for system in systems}
    assert set(outputs) == {"B0", "B1", "B2", "RegBridge"}
    assert all(output.case_id == case.case_id for output in outputs.values())


def test_b2_omits_semantics_without_abstaining_but_keeps_deterministic_link_guard() -> None:
    benchmark = load_frozen_benchmark()
    runner = BaselineRunner()
    stale = next(
        case
        for case in benchmark.cases
        if case.archetype == "stale-content-or-hyperlink"
        and not case.decision_relevant_predicates["selected_leaf"]["hyperlinks"]
        and case.reference.decision.value == "HUMAN_REGULATORY_REVIEW"
        and case.target_context.scenario_mode.value == "prospective_forward_compatibility"
    )
    stale_prediction, _ = runner.run("B2", runner.case_input(stale))
    assert stale_prediction.prediction_source == "genuine_rule_only"
    assert stale_prediction.decision.value == "REUSE_AS_LEGACY_REFERENCE"
    unverified_link = next(
        case
        for case in benchmark.cases
        if case.decision_relevant_predicates["selected_leaf"]["hyperlinks"]
        and not case.decision_relevant_predicates["selected_leaf"]["hyperlinks"][0][
            "author_verified_relevant"
        ]
        and case.target_context.scenario_mode.value == "prospective_forward_compatibility"
    )
    guarded_prediction, _ = runner.run("B2", runner.case_input(unverified_link))
    assert guarded_prediction.decision.value == "HUMAN_REGULATORY_REVIEW"
    assert guarded_prediction.action == "VERIFY_HYPERLINK_RELEVANCE"
