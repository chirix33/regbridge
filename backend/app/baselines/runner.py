from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.analyzer.service import AnalysisService
from app.baselines.direct import (
    DIRECT_OUTPUT_TOKEN_LIMIT,
    contract_fixture_decision,
    prepare_case,
    serialize_direct_request,
    translate_evidence_aliases,
)
from app.baselines.retrieval import BM25Retriever
from app.config import Settings
from app.domain.enums import Decision, LlmMode
from app.domain.models import ModelRunRecord
from app.evaluation.models import (
    BenchmarkCase,
    CaseInput,
    RetrievalTrace,
    SystemName,
    SystemPrediction,
)
from app.graph.models import GraphNeighborhood
from app.llm.models import ModelCompletion, ModelRequest, SemanticRiskOutput
from app.parsers.ectd322 import FixtureCatalog
from app.standards.evidence import EvidenceRegistry

ModelOutput = TypeVar("ModelOutput", bound=BaseModel)


class _DiscardRepository:
    graph: GraphNeighborhood | None = None

    def save(self, result: Any, graph: Any) -> None:
        self.graph = GraphNeighborhood.model_validate(graph)


class OmittedSemanticModel:
    """B2 capability boundary: no semantic findings and no abstention side effect."""

    async def complete(
        self, request: ModelRequest, output_type: type[ModelOutput]
    ) -> ModelCompletion[ModelOutput]:
        output = SemanticRiskOutput(
            fixture_version="1.0.0",
            abstained=False,
            abstain_reason=None,
            findings=(),
            confidence=1,
        )
        return ModelCompletion(
            output=output_type.model_validate(output.model_dump()),
            run=ModelRunRecord(
                mode="disabled",
                status="not_applicable",
                prompt_template_version=request.prompt_template_version,
                model_name="semantic-capability-omitted",
                latency_ms=0,
            ),
        )


class BaselineRunner:
    def __init__(self) -> None:
        self.catalog = FixtureCatalog()
        self.evidence = tuple(sorted(EvidenceRegistry().load(), key=lambda item: item.id))
        self.evidence_by_id = {item.id: item for item in self.evidence}
        self.retriever = BM25Retriever(self.evidence)
        self.graph_snapshots: dict[str, dict[str, Any]] = {}

    def case_input(self, case: BenchmarkCase) -> CaseInput:
        inventory = self.catalog.parse(case.fixture_id)
        if inventory.package_sha256 != case.package_sha256:
            raise ValueError(f"frozen package hash mismatch for {case.case_id}")
        leaf = next(item for item in inventory.leaves if item.id == case.selected_leaf_id)
        dossier = AnalysisService._dossier_evidence(f"artifact-{leaf.id}", leaf)
        return case.to_case_input().model_copy(update={"dossier_evidence": dossier})

    def run(
        self, system: SystemName, case_input: CaseInput
    ) -> tuple[SystemPrediction, RetrievalTrace | None]:
        if system in {"B0", "B1"}:
            return self._direct(system, case_input)
        if system == "B2":
            return self._pipeline(system, case_input, omit_semantic=True), None
        return self._pipeline(system, case_input, omit_semantic=False), None

    def _direct(
        self, system: SystemName, case_input: CaseInput
    ) -> tuple[SystemPrediction, RetrievalTrace | None]:
        prepared = prepare_case(case_input)
        retrieval: RetrievalTrace | None = None
        selected = self.evidence
        if system == "B1":
            retrieval = self.retriever.retrieve(
                case_id=case_input.case_id, query=prepared.serialized
            )
            selected = tuple(self.evidence_by_id[item.evidence_id] for item in retrieval.hits)
        serialized = serialize_direct_request(prepared, selected)
        output = translate_evidence_aliases(contract_fixture_decision(prepared, selected), prepared)
        output_tokens = (len(output.model_dump_json()) + 3) // 4
        if output_tokens > DIRECT_OUTPUT_TOKEN_LIMIT:
            raise ValueError("direct-decision fixture exceeds the fixed output token limit")
        prediction = SystemPrediction(
            system=system,
            case_id=case_input.case_id,
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
            prediction_source="contract_fixture",
            empirical_model_observation=False,
            latency_ms=0,
            requests=1,
            input_tokens=(len(serialized) + 3) // 4,
            output_tokens=output_tokens,
            cost_usd=None,
        )
        return prediction, retrieval

    def _pipeline(
        self, system: SystemName, case_input: CaseInput, *, omit_semantic: bool
    ) -> SystemPrediction:
        inventory = self.catalog.parse(case_input.fixture_id)
        model = OmittedSemanticModel() if omit_semantic else None
        settings = Settings(
            reg_bridge_database_path=Path("results") / "unused-evaluation.sqlite3",
            llm_mode=LlmMode.FIXTURE,
        )
        repository = _DiscardRepository()
        service = AnalysisService(
            settings=settings,
            repository=repository,  # type: ignore[arg-type]
            model=model,
        )
        result = service.analyze(inventory, case_input.selected_leaf_id, case_input.target_context)
        if repository.graph is None:
            raise ValueError("production pipeline did not produce its graph snapshot")
        self.graph_snapshots[f"{system}:{case_input.case_id}"] = repository.graph.model_dump(
            mode="json"
        )
        evidence_ids = tuple(item.id for item in result.evidence)
        requests = 0 if omit_semantic or result.model_run.status == "not_applicable" else 1
        return SystemPrediction(
            system=system,
            case_id=case_input.case_id,
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
            evidence_ids=evidence_ids,
            rule_ids=result.triggered_rule_ids,
            confidence=result.confidence,
            prediction_source=("genuine_rule_only" if omit_semantic else "hybrid_contract_fixture"),
            empirical_model_observation=False,
            latency_ms=result.model_run.latency_ms,
            requests=requests,
            input_tokens=result.model_run.input_tokens or 0,
            output_tokens=result.model_run.output_tokens or 0,
            cost_usd=None,
        )
