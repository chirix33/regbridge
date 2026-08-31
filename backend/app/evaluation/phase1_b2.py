"""Fresh rule-only rescore from the isolated development bundle; no model or catalog lookup."""

from dataclasses import dataclass
from typing import Any

from app.analyzer.service import AnalysisService
from app.baselines.runner import OmittedSemanticModel, _DiscardRepository
from app.config import REPOSITORY_ROOT, Settings
from app.domain.enums import Decision, LlmMode
from app.domain.vocabulary import action_vocabulary_disclosure, output_vocabulary
from app.evaluation.live_configuration import configuration_material, content_digest
from app.evaluation.metrics import score_system
from app.evaluation.models import CaseInput, MetricsReport, SystemPrediction
from app.evaluation.phase1_bundle import Phase1Bundle, Phase1FixtureMetadata
from app.parsers.ectd322 import parse_directory
from app.standards.evidence import EvidenceRegistry

B2_RESULT_STATUS = "genuine deterministic experimental output"


def scoring_contract() -> dict[str, Any]:
    return {
        "output_vocabulary": output_vocabulary(),
        "action_vocabulary_disclosure": action_vocabulary_disclosure(),
        "decision_scoring_policy": "option-a-exact-match-three-represented-reference-classes",
    }


@dataclass(frozen=True)
class B2Rescore:
    configuration_sha256: str
    bundle_content_sha256: str
    contract: dict[str, Any]
    predictions: tuple[SystemPrediction, ...]
    reports: tuple[MetricsReport, ...]

    def validate_for_comparison(self, bundle: Phase1Bundle) -> None:
        if self.configuration_sha256 != content_digest(configuration_material()):
            raise ValueError("Comparison blocked: B2 configuration digest mismatch")
        if self.contract != scoring_contract():
            raise ValueError("Comparison blocked: B2 scoring contract mismatch")
        if self.bundle_content_sha256 != content_digest(bundle.model_dump(mode="json")):
            raise ValueError("Comparison blocked: B2 bundle digest mismatch")
        expected = {item.case_id for item in bundle.case_inputs}
        if len(self.predictions) != len(expected) or {
            item.case_id for item in self.predictions
        } != expected:
            raise ValueError("Comparison blocked: B2 coverage is incomplete")
        for item in self.predictions:
            SystemPrediction.model_validate(item.model_dump())
            if (item.system != "B2" or item.prediction_source != "genuine_rule_only"
                    or item.requests or item.empirical_model_observation):
                raise ValueError("Comparison blocked: B2 is not genuine rule-only output")

    def artifact(self) -> dict[str, Any]:
        return {
            "run_type": "deterministic_rule_only_rescore",
            "result_status": B2_RESULT_STATUS,
            "empirical_model_run": False,
            "eligible_for_performance_claims": False,
            "scope": "phase1-development-train-dev-only",
            "current_fda_operational_availability": "not_operational",
            "expert_validated": False,
            "configuration_sha256": self.configuration_sha256,
            "bundle_content_sha256": self.bundle_content_sha256,
            "scoring_contract": self.contract,
            "model_calls": 0,
            "latency_policy": "model latency only; zero model calls, no pipeline timing claim",
            "predictions": [item.model_dump(mode="json") for item in self.predictions],
            "reports": [item.model_dump(mode="json") for item in self.reports],
        }


async def _predict(
    case_input: CaseInput, fixture: Phase1FixtureMetadata,
) -> SystemPrediction:
    """No reference label, rationale, family, or expected action reaches inference."""
    fixture_root = (REPOSITORY_ROOT / "data/demo-cases").resolve()
    fixture_path = (fixture_root / fixture.relative_path).resolve()
    if not fixture_path.is_relative_to(fixture_root) or fixture.fixture_id != case_input.fixture_id:
        raise ValueError("B2 isolated fixture path or membership mismatch")
    inventory = parse_directory(
        fixture_path, fixture_id=fixture.fixture_id,
        author_verified_relevant_hyperlink_ids=fixture.author_verified_relevant_hyperlink_ids,
    )
    leaf = next(item for item in inventory.leaves if item.id == case_input.selected_leaf_id)
    if (inventory.package_sha256 != case_input.package_sha256
            or leaf.file_sha256 != case_input.selected_file_sha256):
        raise ValueError("B2 isolated input hash mismatch")
    service = AnalysisService(
        settings=Settings(llm_mode=LlmMode.DISABLED), model=OmittedSemanticModel(),
        repository=_DiscardRepository(),  # type: ignore[arg-type]
    )
    result = await service.analyze_async(inventory, leaf.id, case_input.target_context)
    return SystemPrediction(
        system="B2", case_id=case_input.case_id, decision=result.decision,
        severity=result.severity, action=result.repair.type,
        human_review_required=result.human_approval_required,
        unconditional_reuse=(
            result.decision == Decision.REUSE_AS_LEGACY_REFERENCE
            and result.repair.type == "NO_MATERIAL_REPAIR" and not result.human_approval_required
        ),
        rationale=result.rationale, evidence_ids=tuple(item.id for item in result.evidence),
        rule_ids=result.triggered_rule_ids, confidence=result.confidence,
        prediction_source="genuine_rule_only", empirical_model_observation=False,
        latency_ms=0, requests=0, input_tokens=0, output_tokens=0, cost_usd=0,
    )


async def rescore_b2(bundle: Phase1Bundle, *, seed: int) -> B2Rescore:
    # Validate even a model_copy-mutated bundle before any fixture preparation.
    bundle = Phase1Bundle.model_validate(bundle.model_dump())
    configuration_sha256 = content_digest(configuration_material())
    contract = scoring_contract()
    membership = {item.case_id: item.split for item in bundle.cases}
    metadata = {item.fixture_id: item for item in bundle.fixture_metadata}
    if (len(metadata) != len(bundle.fixture_metadata)
            or set(metadata) != {item.fixture_id for item in bundle.case_inputs}):
        raise ValueError("B2 isolated fixture catalog membership mismatch")
    predictions = []
    for case_input in bundle.case_inputs:
        if membership.get(case_input.case_id) not in {"train", "development"}:
            raise ValueError("B2 Phase 1 membership guard rejected input")
        predictions.append(await _predict(case_input, metadata[case_input.fixture_id]))

    # Reference labels are joined only here, after all predictions exist.
    evidence_ids = frozenset(item.id for item in EvidenceRegistry().load())
    reports = []
    for scope, splits in (
        ("phase1-train", {"train"}), ("phase1-development", {"development"}),
        ("phase1-train-development", {"train", "development"}),
    ):
        cases = tuple(item for item in bundle.cases if item.split in splits)
        ids = {item.case_id for item in cases}
        report, _ = score_system(
            cases=cases, predictions=tuple(item for item in predictions if item.case_id in ids),
            retrieval_traces=(), scope=scope, seed=seed, regulatory_evidence_ids=evidence_ids,
        )
        reports.append(report)
    result = B2Rescore(
        configuration_sha256, content_digest(bundle.model_dump(mode="json")), contract,
        tuple(predictions), tuple(reports),
    )
    result.validate_for_comparison(bundle)
    return result
