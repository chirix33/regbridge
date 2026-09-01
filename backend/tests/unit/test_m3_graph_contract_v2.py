import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from app.analyzer.repository import AnalysisRepository
from app.analyzer.service import AnalysisPipelineError, AnalysisService
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import (
    EdgeType,
    EnforcementMode,
    LlmMode,
    NodeType,
    ReviewStatus,
    ScenarioMode,
)
from app.domain.models import ModelRunRecord
from app.evaluation.benchmark import load_frozen_benchmark
from app.graph.models import GRAPH_SCHEMA_VERSION, GraphEdge, GraphNeighborhood, GraphNode
from app.llm.models import ModelCompletion, ModelRequest, SemanticRiskOutput
from app.llm.protocol import StructuredModel
from app.llm.responses import ResponsesStructuredModel
from app.parsers.ectd322 import FixtureCatalog
from pydantic import SecretStr, ValidationError


def _node(node_id: str, node_type: NodeType, **kwargs: Any) -> GraphNode:
    return GraphNode(id=node_id, type=node_type, label=node_id, **kwargs)


def _valid_keyword_graph() -> GraphNeighborhood:
    return GraphNeighborhood(
        analysis_id="analysis-synthetic",
        nodes=(
            _node("finding-1", NodeType.MODEL_FINDING, review_status=ReviewStatus.CANDIDATE),
            _node(
                "occurrence-1",
                NodeType.DOSSIER_EVIDENCE,
                properties={"evidence_kind": "metadata"},
            ),
            _node("keyword-1", NodeType.KEYWORD),
        ),
        edges=(
            GraphEdge(
                id="edge-cites", source="finding-1", target="occurrence-1",
                type=EdgeType.CITES, label="cites", review_status=ReviewStatus.CANDIDATE,
            ),
            GraphEdge(
                id="edge-about", source="finding-1", target="keyword-1",
                type=EdgeType.ABOUT, label="about", review_status=ReviewStatus.CANDIDATE,
            ),
            GraphEdge(
                id="edge-observes", source="occurrence-1", target="keyword-1",
                type=EdgeType.OBSERVES, label="observes",
            ),
        ),
        text_alternative=("synthetic",),
    )


def test_graph_schema_v2_contract_and_keyword_agreement() -> None:
    graph = _valid_keyword_graph()
    assert GRAPH_SCHEMA_VERSION == "2.0.0"
    assert {edge.type for edge in graph.edges} == {
        EdgeType.CITES, EdgeType.ABOUT, EdgeType.OBSERVES,
    }

    with pytest.raises(ValidationError, match="domain/range"):
        GraphNeighborhood(
            analysis_id="analysis-invalid-cites-keyword",
            nodes=(
                _node("finding-1", NodeType.MODEL_FINDING, review_status=ReviewStatus.CANDIDATE),
                _node("keyword-1", NodeType.KEYWORD),
            ),
            edges=(GraphEdge(
                id="edge-invalid", source="finding-1", target="keyword-1",
                type=EdgeType.CITES, label="invalid", review_status=ReviewStatus.CANDIDATE,
            ),),
            text_alternative=("invalid",),
        )

    payload = graph.model_dump(mode="json")
    payload["edges"] = [edge for edge in payload["edges"] if edge["type"] != "CITES"]
    with pytest.raises(ValidationError, match="ABOUT requires occurrence-level CITES"):
        GraphNeighborhood.model_validate(payload)

    mismatch = graph.model_dump(mode="json")
    mismatch["nodes"].append(_node("keyword-2", NodeType.KEYWORD).model_dump(mode="json"))
    next(edge for edge in mismatch["edges"] if edge["type"] == "ABOUT")["target"] = "keyword-2"
    with pytest.raises(ValidationError, match="exactly agree"):
        GraphNeighborhood.model_validate(mismatch)


class MetadataFindingModel:
    async def complete(
        self, request: ModelRequest, output_type: type[SemanticRiskOutput],
    ) -> ModelCompletion[SemanticRiskOutput]:
        evidence = next(
            item for item in request.evidence if getattr(item, "kind", None) == "metadata"
        )
        output = output_type.model_validate({
            "fixture_version": "1.0.0",
            "abstained": False,
            "abstain_reason": None,
            "findings": [{
                "id": "finding-metadata-occurrence",
                "basis": "observation",
                "summary": "The supplied metadata occurrence is the subject of this signal.",
                "severity": "low",
                "evidence_ids": [evidence.id],
                "category": "ambiguous_reference",
            }],
            "confidence": 0.5,
        })
        return ModelCompletion(
            output=output,
            run=ModelRunRecord(
                mode="fixture", status="completed", prompt_template_version="1.0.0",
                model_name="synthetic-metadata-finding", latency_ms=0,
            ),
        )


class FirstOccurrenceFindingModel:
    async def complete(
        self, request: ModelRequest, output_type: type[SemanticRiskOutput],
    ) -> ModelCompletion[SemanticRiskOutput]:
        evidence = request.evidence[0]
        output = output_type.model_validate({
            "fixture_version": "1.0.0", "abstained": False, "abstain_reason": None,
            "findings": [{
                "id": "finding-first-occurrence", "basis": "observation",
                "summary": "A signal grounded in the supplied dossier occurrence.",
                "severity": "low", "evidence_ids": [evidence.id],
                "category": "ambiguous_reference",
            }],
            "confidence": 0.5,
        })
        return ModelCompletion(
            output=output,
            run=ModelRunRecord(
                mode="fixture", status="completed", prompt_template_version="1.0.0",
                model_name="synthetic-first-occurrence", latency_ms=0,
            ),
        )


@pytest.mark.asyncio
async def test_every_frozen_case_b_metadata_finding_commits_to_graph(tmp_path: Path) -> None:
    cases = tuple(case for case in load_frozen_benchmark().cases if case.case_id.startswith("B"))
    assert len(cases) == 10
    catalog = FixtureCatalog()
    for index, case in enumerate(cases):
        inventory = catalog.parse(case.fixture_id)
        target = case.target_context.model_copy(update={
            "scenario_mode": ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        })
        service = AnalysisService(
            model=cast(StructuredModel, MetadataFindingModel()),
            repository=AnalysisRepository(tmp_path / f"case-b-{index}.sqlite3"),
            settings=Settings(llm_mode=LlmMode.FIXTURE),
        )
        result = await service.analyze_async(inventory, case.selected_leaf_id, target)
        graph = service.graph(result.id)
        finding_id = "finding-finding-metadata-occurrence"
        cites = [
            edge for edge in graph.edges
            if edge.source == finding_id and edge.type == EdgeType.CITES
        ]
        about = [
            edge for edge in graph.edges
            if edge.source == finding_id and edge.type == EdgeType.ABOUT
        ]
        assert cites and about, case.case_id
        occurrence = next(node for node in graph.nodes if node.id == cites[0].target)
        assert occurrence.type == NodeType.DOSSIER_EVIDENCE
        assert {edge.target for edge in graph.edges
                if edge.source == occurrence.id and edge.type == EdgeType.OBSERVES} == {
                    edge.target for edge in about
                }
        assert occurrence.properties["owner"] == result.source_artifact.id
        assert occurrence.properties["locator"]
        assert occurrence.properties["provenance"]["file_sha256"]
        finding = next(node for node in graph.nodes if node.id == finding_id)
        assert finding.review_status == ReviewStatus.CANDIDATE
        assert all(edge.enforcement_mode == EnforcementMode.DISABLED for edge in cites + about)


@pytest.mark.asyncio
async def test_case_a_and_c_occurrences_fit_citation_domain_without_analogous_failure(
    tmp_path: Path,
) -> None:
    cases = tuple(
        case for case in load_frozen_benchmark().cases
        if case.case_id.startswith(("A", "C"))
    )
    assert len(cases) == 20
    catalog = FixtureCatalog()
    exercised = 0
    for index, case in enumerate(cases):
        inventory = catalog.parse(case.fixture_id)
        selected_leaf = next(leaf for leaf in inventory.leaves if leaf.id == case.selected_leaf_id)
        if not AnalysisService._dossier_evidence(f"artifact-{selected_leaf.id}", selected_leaf):
            # SemanticFinding requires at least one supplied occurrence, so this case cannot
            # construct the analogous edge at all.
            continue
        target = case.target_context.model_copy(update={
            "scenario_mode": ScenarioMode.PROSPECTIVE_FORWARD_COMPATIBILITY,
        })
        service = AnalysisService(
            model=cast(StructuredModel, FirstOccurrenceFindingModel()),
            repository=AnalysisRepository(tmp_path / f"case-ac-{index}.sqlite3"),
            settings=Settings(llm_mode=LlmMode.FIXTURE),
        )
        result = await service.analyze_async(inventory, case.selected_leaf_id, target)
        graph = service.graph(result.id)
        cites = [
            edge for edge in graph.edges
            if edge.source == "finding-finding-first-occurrence" and edge.type == EdgeType.CITES
        ]
        assert len(cites) == 1, case.case_id
        cited = next(node for node in graph.nodes if node.id == cites[0].target)
        assert cited.type == NodeType.DOSSIER_EVIDENCE
        assert cited.properties["evidence_kind"] in {"text", "hyperlink", "metadata"}
        exercised += 1
    assert exercised >= 10  # All Case C records and any Case A record with extracted evidence.


@pytest.mark.asyncio
async def test_b003_saved_first_response_replays_without_edit_under_graph_v2(
    tmp_path: Path,
) -> None:
    source = (
        REPOSITORY_ROOT / "results" / "live" /
        "m3-live-phase1-20260831T225610474936Z" / "attempts.jsonl"
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    record = next(
        json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
        if (json.loads(line)["system"], json.loads(line)["case_id"],
            json.loads(line)["attempt"]["attempt_index"]) == ("RegBridge", "B003", 1)
    )
    saved_text = record["attempt"]["final_json_text"]
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.content.decode())
        return httpx.Response(200, json={
            "id": "response-replay-b003",
            "status": "completed",
            "model": "gpt-5.5-2026-04-23",
            "output_text": saved_text,
            "usage": {
                "input_tokens": 899,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 457,
                "output_tokens_details": {"reasoning_tokens": 321},
            },
        })

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 125,
        transport=httpx.MockTransport(handler),
    )
    case = next(case for case in load_frozen_benchmark().cases if case.case_id == "B003")
    inventory = FixtureCatalog().parse(case.fixture_id)
    service = AnalysisService(
        model=model,
        repository=AnalysisRepository(tmp_path / "b003-replay.sqlite3"),
        settings=Settings(
            llm_mode=LlmMode.LIVE,
            llm_model="gpt-5.5",
            llm_base_url="https://example.invalid/v1",
            llm_api_key=SecretStr("test"),
        ),
    )
    result = await service.analyze_async(inventory, case.selected_leaf_id, case.target_context)
    graph = service.graph(result.id)
    finding_id = "finding-finding-001"
    cited = {edge.target for edge in graph.edges
             if edge.source == finding_id and edge.type == EdgeType.CITES}
    about = {edge.target for edge in graph.edges
             if edge.source == finding_id and edge.type == EdgeType.ABOUT}
    metadata_occurrence = next(
        node for node in graph.nodes
        if node.id in cited and node.properties.get("evidence_kind") == "metadata"
    )
    observed = {edge.target for edge in graph.edges
                if edge.source == metadata_occurrence.id and edge.type == EdgeType.OBSERVES}
    assert about == observed == {"keyword-manufacturer-all"}
    assert metadata_occurrence.properties["raw_value"] == " ALL "
    assert metadata_occurrence.properties["owner"] == result.source_artifact.id
    assert metadata_occurrence.properties["locator"]
    assert metadata_occurrence.properties["provenance"]["evidence_id"].endswith(
        "metadata-manufacturer"
    )
    wire = requests[0].casefold()
    durable_evidence_id = metadata_occurrence.properties["provenance"]["evidence_id"].casefold()
    for leaked in (
        "b003",
        case.fixture_id.casefold(),
        durable_evidence_id,
        metadata_occurrence.properties["locator"].casefold(),
    ):
        assert leaked not in wire
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", [
    "fabricated-evidence-999",
    "leaf-other-case-metadata-manufacturer",
    "keyword-manufacturer-all",
])
async def test_unsupplied_cross_case_and_concept_citations_are_invalid_output(
    citation: str,
) -> None:
    request = ModelRequest(
        fixture_lookup_key="fixture-private",
        task="Inspect the supplied occurrence.",
        context={"authority": "FDA"},
        evidence=(),
        prompt_template_version="1.0.0",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": "completed",
            "output_text": json.dumps({
                "fixture_version": "1.0.0", "abstained": False, "abstain_reason": None,
                "findings": [{
                    "id": "finding-001", "basis": "observation", "summary": "Synthetic",
                    "severity": "low", "evidence_ids": [citation],
                    "category": "ambiguous_reference",
                }],
                "confidence": 0.5,
            }),
        })

    model = ResponsesStructuredModel(
        base_url="https://example.invalid/v1", api_key="test", model="gpt-5.5",
        timeout_seconds=1, count_final_tokens=lambda _: 50,
        transport=httpx.MockTransport(handler),
    )
    from app.evaluation import live_phase1 as live

    attempts, output, failure = await live._retry_live_call(
        model=model,
        first_authorized_request=False,
        call=lambda: model.complete(request, SemanticRiskOutput),
    )
    assert output is None and failure == "unsupported_citation"
    assert len(attempts) == 1 and attempts[0].retryable is False


def test_graph_and_persistence_failures_leave_no_partial_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = next(case for case in load_frozen_benchmark().cases if case.case_id == "A006")
    inventory = FixtureCatalog().parse(case.fixture_id)
    source = AnalysisService(
        repository=AnalysisRepository(tmp_path / "source.sqlite3"),
        settings=Settings(llm_mode=LlmMode.FIXTURE),
    )
    result = source.analyze(inventory, case.selected_leaf_id, case.target_context)
    graph = source.graph(result.id)

    target = AnalysisRepository(tmp_path / "target.sqlite3")
    with target._connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_analysis BEFORE INSERT ON analyses "
            "BEGIN SELECT RAISE(ABORT, 'synthetic persistence failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic persistence failure"):
        target.save(result, graph)
    with target._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0

    class RecordingRepository:
        save_calls = 0

        def save(self, *_: Any) -> None:
            self.save_calls += 1

    repository = RecordingRepository()
    service = AnalysisService(
        repository=repository,  # type: ignore[arg-type]
        settings=Settings(llm_mode=LlmMode.FIXTURE),
    )
    monkeypatch.setattr(
        "app.analyzer.service.build_neighborhood",
        lambda _: (_ for _ in ()).throw(ValueError("synthetic graph failure")),
    )
    with pytest.raises(AnalysisPipelineError, match="graph:ValueError"):
        service.analyze(inventory, case.selected_leaf_id, case.target_context)
    assert repository.save_calls == 0
